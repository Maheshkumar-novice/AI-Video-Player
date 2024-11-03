import json
from pathlib import Path

import spacy

nlp = spacy.load("en_core_web_trf")


def extract_names(title):
    doc = nlp(title)
    names = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
    return names


title_names = {}
for path in Path().glob("videos/*.mp4"):
    title = path.stem
    names = extract_names(title)
    if not names:
        continue
    title_names[title] = names

f = Path("title_names.json").open("w")
json.dump(title_names, f, indent=4, sort_keys=True)
f.close()
