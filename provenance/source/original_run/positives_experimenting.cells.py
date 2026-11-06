# --- cell 10 (first-pass parse and radiology regex)
def create_valid_jsons(pos_pairs):
    # 1) split into successful and failed pairs
    clean_pairs = []                       # will hold the non-empty, parsed objects
    failed_pairs = []
    for raw in pos_pairs:                  
        try:
            obj = json.loads(raw)          # turn the string into a Python list / dict
        except json.JSONDecodeError:
            failed_pairs.append(raw)                 
            continue                       

        if obj:                           
            clean_pairs.append(obj)      

    # 2) fix the failed pairs
    fixed_pairs = []
    for raw in failed_pairs:
        raw = raw.strip()
        wrapped = '[' + re.sub(r'}\s*{', '},{', raw) + ']'
        fixed_pairs.append(json.loads(wrapped))

    if len(fixed_pairs) != len(failed_pairs):
        print(f"WARNING: {len(fixed_pairs)} fixed pairs, but {len(failed_pairs)} failed pairs")
    return clean_pairs + fixed_pairs

# --- cell 11 (first-pass parse and radiology regex)
clean_pairs = create_valid_jsons(pos_pairs)

# --- cell 14 (first-pass parse and radiology regex)
import re
from functools import partial

# 1. RADIOLOGY-STYLE MODALITIES
#    (cross-sectional + ultrasound + radionuclide)

RADIOLOGY_MODALITIES = {
    # Radiography & CT
    "xray":              r"\b(x[- ]?ray|radiograph|plain[- ]?film)\b",
    "fluoroscopy":       r"\b(fluoroscopy|fluoroscopic)\b",
    "angiography":       r"\b(angiography|angiogram|dsa|digital subtraction angiography)\b",
    "ct":                r"\b(ct|hrct|h[- ]?r[- ]?ct|high[- ]?resolution[- ]?ct|computed tomography|cat[- ]?scan)\b",
    "spectral_ct":       r"\b(dual[- ]?energy|spectral[- ]?ct)\b",
    "dexa":              r"\b(dxa|dexa|dual[- ]?energy x[- ]?ray absorptiometry)\b",
    "mammography":       r"\b(mammography|mammogram|digital breast tomosynthesis|dbt)\b",

    # MRI family
    "mri":               r"\b(mri|magnetic resonance imaging)\b",
    "mra":               r"\b(mra|mr[- ]?angiography)\b",
    "mrs":               r"\b(mrs|mr[- ]?spectroscopy)\b",
    "fmri":              r"\b(f[- ]?mri|functional mri)\b",
    "dti":               r"\b(dti|diffusion tensor imaging)\b",

    # Nuclear medicine
    "pet":               r"\b(pet|positron emission tomography)\b",
    "spect":             r"\b(spect|single photon emission computed tomography)\b",

    # Ultrasound & elastography
    "ultrasound":        r"\b(ultra.?sound|sonograph(?:y|ic)?|b[- ]?scan)\b",
    "doppler":           r"\b(doppler (ultra.?sound)?|color flow doppler|pulsed doppler)\b",
    "echocardiography":  r"\b(echo(?:cardiography|cardiogram)|ttee|tte|toe|tee)\b",
    "elastography":      r"\b(elastography|shear[- ]?wave elastography|transient elastography)\b",
}

# 2. OPTICAL / MICROSCOPY MODALITIES
OPTICAL_MODALITIES = {
    # Optical & photographic
    "oct":               r"\b(oct|optical coherence tomography|sd[- ]?oct|spectral domain oct)\b",
    "fundus":            r"\b(fundus photography|fundus image|retinal photograph(?:y)?)\b",
    "fluorescence":      r"\b(fluorescence (imaging|microscopy))\b",
    "photoacoustic":     r"\b(photoacoustic (imaging|tomography)|pat)\b",
    "thermography":      r"\b(thermal imaging|infrared thermography|thermography)\b",
}

# 3. VISUALISATION / ENDOSCOPIC MODALITIES
VISUAL_MODALITIES = {
    "endoscopy":         r"\b(endoscopy|endoscopic|gastroscopy|colonoscopy|bronchoscopy|arthroscopy)\b",
    "laparoscopy":       r"\b(laparoscopy|laparoscopic)\b",
    "capsule_endoscopy": r"\b(capsule endoscopy|pill[- ]?cam)\b",
    "ivus":              r"\b(ivus|intravascular ultrasound)\b",
    "oct_ivus":          r"\b(ivoct|intravascular optical coherence tomography)\b",
    "clinical_photo":    r"\b(clinical (photo(?:graph)?|image)|macrophotography)\b",
    # Microscopy & pathology slides
    "light_microscopy":  r"\b(light microscopy|bright[- ]?field|phase[- ]?contrast)\b",
    "confocal":          r"\b(confocal microscopy|lscm|laser scanning confocal)\b",
    "electron_microscopy": r"\b((transmission|scanning) electron microscopy|tem|sem)\b",
    "histopathology":    r"\b(histopathology|histology|photomicrograph(?:y)?)\b",
    "immunohistochemistry": r"\b(ihc|immunohistochem(?:istry)?)\b",
    "dermatoscopy":      r"\b(dermatoscopy|dermoscopy)\b",
}


# 4.  CONVENIENCE MERGERS
ALL_MODALITIES = {
    **RADIOLOGY_MODALITIES,
    **OPTICAL_MODALITIES,
    **VISUAL_MODALITIES,
}

# 5.  LOOK-UP HELPER
def make_canonical_modality_fn(pool: dict):
    """Return a function that maps free text to canonical key (or None)."""
    def canonical_modality(text: str):
        for key, pattern in pool.items():
            if re.search(pattern, text, flags=re.I):
                return key
        return None
    return canonical_modality

# ready-made detectors
canonical_modality = make_canonical_modality_fn(ALL_MODALITIES)
radiology_modality = make_canonical_modality_fn(RADIOLOGY_MODALITIES)
optical_modality = make_canonical_modality_fn(OPTICAL_MODALITIES)
visual_modality = make_canonical_modality_fn(VISUAL_MODALITIES)

# --- cell 15 (first-pass parse and radiology regex)
def split_into_modalities(modality_func: callable):
    lst = []
    for pair in clean_pairs:
        if type(pair) is list:
            for item in pair:
                if modality_func(item['modality']) is not None:
                    lst.append(item)
        elif type(pair) is dict:
            if modality_func(pair['modality']) is not None:
                lst.append(pair)
    return lst

# --- cell 16 (first-pass parse and radiology regex)
radiology_modalities = split_into_modalities(radiology_modality)
optical_modalities = split_into_modalities(optical_modality)
visual_modalities = split_into_modalities(visual_modality)
canonical_modalities = split_into_modalities(canonical_modality)

# --- cell 19 (first-pass parse and radiology regex)
with open(lists_path/'radiology_pos_pairs.json', 'w') as f:
    json.dump(radiology_modalities, f)

with open(lists_path/'optical_pos_pairs.json', 'w') as f:
    json.dump(optical_modalities, f)

with open(lists_path/'visual_pos_pairs.json', 'w') as f:
    json.dump(visual_modalities, f)

with open(lists_path/'canonical_pos_pairs.json', 'w') as f:
    json.dump(canonical_modalities, f)
