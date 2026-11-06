# --- lines 139-171 (descriptor text and field cleaning; pair-key and caption helpers)
def canonical_pair(value: Any) -> tuple[str, str]:
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(part).strip() for part in value]
    else:
        raise ValueError(f"Unsupported pair_id type: {type(value).__name__}")

    if len(items) != 2 or not all(items):
        raise ValueError(f"Expected exactly two nonempty image IDs, got: {value!r}")
    if items[0] == items[1]:
        raise ValueError(f"Self-pair is not valid: {value!r}")
    return tuple(sorted((items[0], items[1])))


def clean_field(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_short_caption(modality: str, anatomy: str, diagnosis: str) -> str:
    parts: list[str] = []
    if diagnosis:
        parts.append(diagnosis)
    if anatomy:
        parts.append(f"in the {anatomy}")
    if modality:
        parts.append(f"on {modality}")
    caption = " ".join(parts).strip()
    if caption and not caption.endswith("."):
        caption += "."
    return caption

# --- lines 206-367 (descriptor resolution; exact-text descriptor recovery and selected_source)
def load_source_index(
    sources: list[SourceSpec],
) -> tuple[
    dict[tuple[str, str], list[SourceAnnotation]],
    dict[str, dict[str, int]],
]:
    index: dict[tuple[str, str], list[SourceAnnotation]] = defaultdict(list)
    record_counts: dict[str, dict[str, int]] = {}

    for source in sources:
        payload = load_json(source.path)
        if not isinstance(payload, list):
            raise ValueError(f"{source.path} must contain a top-level JSON list")
        indexed_count = 0
        skipped_invalid_pair_count = 0

        for record_index, record in enumerate(payload):
            if not isinstance(record, dict):
                skipped_invalid_pair_count += 1
                continue
            if "pair_id" not in record:
                skipped_invalid_pair_count += 1
                continue
            try:
                pair = canonical_pair(record["pair_id"])
            except ValueError:
                # Source artifacts contain a small number of malformed/self pairs.
                # They cannot match a valid final pair, so index the valid subset and
                # expose the skipped count in the validation report.
                skipped_invalid_pair_count += 1
                continue
            modality = clean_field(record.get("modality"))
            anatomy = clean_field(record.get("anatomy"))
            diagnosis = clean_field(record.get("diagnosis"))
            caption = build_short_caption(modality, anatomy, diagnosis)
            index[pair].append(
                SourceAnnotation(
                    source_name=source.name,
                    source_path=str(source.path.resolve()),
                    source_priority=source.priority,
                    source_record_index=record_index,
                    pair=pair,
                    modality=modality,
                    anatomy=anatomy,
                    diagnosis=diagnosis,
                    pair_text=caption,
                )
            )
            indexed_count += 1

        record_counts[source.name] = {
            "total_records": len(payload),
            "indexed_records": indexed_count,
            "skipped_invalid_pair_records": skipped_invalid_pair_count,
        }

    return index, record_counts


def resolve_final_pairs(
    pairs_path: Path,
    texts_path: Path,
    source_index: dict[tuple[str, str], list[SourceAnnotation]],
) -> tuple[list[PairAnnotation], dict[str, Any]]:
    raw_pairs = load_json(pairs_path)
    raw_texts = load_json(texts_path)
    if not isinstance(raw_pairs, list) or not isinstance(raw_texts, list):
        raise ValueError("pairs and texts inputs must both be top-level JSON lists")
    if len(raw_pairs) != len(raw_texts):
        raise ValueError(
            f"Pair/text length mismatch: {len(raw_pairs)} != {len(raw_texts)}"
        )

    seen_pairs: set[tuple[str, str]] = set()
    resolved: list[PairAnnotation] = []
    source_selection_counts: Counter[str] = Counter()
    matching_source_count_distribution: Counter[int] = Counter()
    exact_candidate_count_distribution: Counter[int] = Counter()

    for position, (raw_pair, raw_text_list) in enumerate(zip(raw_pairs, raw_texts)):
        pair = canonical_pair(raw_pair)
        if pair in seen_pairs:
            raise ValueError(f"Duplicate final pair at position {position}: {pair}")
        seen_pairs.add(pair)

        if (
            not isinstance(raw_text_list, list)
            or len(raw_text_list) != 1
            or not isinstance(raw_text_list[0], str)
            or not raw_text_list[0].strip()
        ):
            raise ValueError(
                f"Expected one nonempty pair text at position {position}, "
                f"got {raw_text_list!r}"
            )
        pair_text = raw_text_list[0]

        candidates = source_index.get(pair, [])
        exact = [candidate for candidate in candidates if candidate.pair_text == pair_text]
        if not exact:
            examples = [candidate.pair_text for candidate in candidates[:3]]
            raise ValueError(
                f"No structured record exactly regenerates pair text for {pair}: "
                f"target={pair_text!r}; candidate examples={examples!r}"
            )

        raw_triples = {candidate.raw_triple for candidate in exact}
        if len(raw_triples) != 1:
            raise ValueError(
                f"Exact text match maps to conflicting triples for {pair}: "
                f"{sorted(raw_triples)!r}"
            )

        exact.sort(
            key=lambda item: (
                item.source_priority,
                item.source_record_index,
                item.source_name,
            )
        )
        selected = exact[0]
        matching_sources = tuple(
            sorted(
                {
                    (candidate.source_name, candidate.source_record_index)
                    for candidate in exact
                }
            )
        )
        norm = normalized_triple(*selected.raw_triple)
        resolved.append(
            PairAnnotation(
                pair=pair,
                pair_text=pair_text,
                modality=selected.modality,
                anatomy=selected.anatomy,
                diagnosis=selected.diagnosis,
                normalized_modality=norm[0],
                normalized_anatomy=norm[1],
                normalized_diagnosis=norm[2],
                selected_source=selected.source_name,
                selected_source_record_index=selected.source_record_index,
                matching_sources=matching_sources,
            )
        )
        source_selection_counts[selected.source_name] += 1
        matching_source_count_distribution[len(matching_sources)] += 1
        exact_candidate_count_distribution[len(exact)] += 1

    resolved.sort(key=lambda item: item.pair)
    diagnostics = {
        "source_selection_counts": dict(sorted(source_selection_counts.items())),
        "matching_source_record_count_distribution": {
            str(key): value
            for key, value in sorted(matching_source_count_distribution.items())
        },
        "exact_candidate_count_distribution": {
            str(key): value
            for key, value in sorted(exact_candidate_count_distribution.items())
        },
    }
    return resolved, diagnostics

# --- lines 555-573 (long CSV columns)
LONG_FIELDS = [
    "image_id",
    "image_path",
    "split",
    "pair_role",
    "partner_image_id",
    "source_pair_left",
    "source_pair_right",
    "pair_text",
    "modality",
    "anatomy",
    "diagnosis",
    "normalized_modality",
    "normalized_anatomy",
    "normalized_diagnosis",
    "selected_source",
    "selected_source_record_index",
    "matching_sources",
]

# --- lines 1092-1118 (source precedence; source files and priority)
    source_specs = [
        SourceSpec(
            "legacy_labeled_pos",
            workspace / "<DATA_ROOT>" / "labeled_pos_pairs.json",
            0,
        ),
        SourceSpec(
            "legacy_recovered",
            workspace / "<DATA_ROOT>" / "new_radiology_labeled_pairs_recovered.json",
            1,
        ),
        SourceSpec(
            "legacy_compound_canonical",
            workspace / "<DATA_ROOT>" / "compound_canonical_labeled_pairs.json",
            2,
        ),
        SourceSpec(
            "repro_labeled_positive_pairs",
            workspace
            / "<DATA_ROOT>"
            / "repro_positive_pairs_pipeline"
            / "outputs"
            / "postprocessed"
            / "labeled_positive_pairs.json",
            3,
        ),
    ]
