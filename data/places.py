"""Place gazetteer for Nepal property listings: district names, their common misspellings,
and the towns / municipalities buyers search by. Used to turn free-text addresses and
titles ("Arghaun, Lekhnath, Pokhara", "Land sale near Birtamod chowk") into
(locality, city, district)."""
import re

# District name (and common spellings) -> district.
DISTRICT_ALIASES = {
    "kathmandu": "Kathmandu", "kathamandu": "Kathmandu", "kathmndu": "Kathmandu", "ktm": "Kathmandu",
    "lalitpur": "Lalitpur", "laliltpur": "Lalitpur", "lalitpr": "Lalitpur", "bhaktapur": "Bhaktapur", "bkt": "Bhaktapur",
    "kaski": "Kaski", "chitwan": "Chitwan", "chitawan": "Chitwan", "rupandehi": "Rupandehi", "morang": "Morang",
    "sunsari": "Sunsari", "jhapa": "Jhapa", "kavre": "Kavrepalanchok", "kavrepalanchok": "Kavrepalanchok",
    "kabhre": "Kavrepalanchok", "kavrepalanchowk": "Kavrepalanchok", "kabhrepalanchok": "Kavrepalanchok", "makwanpur": "Makwanpur", "makawanpur": "Makwanpur", "nuwakot": "Nuwakot",
    "kailali": "Kailali", "banke": "Banke", "dang": "Dang", "surkhet": "Surkhet", "parsa": "Parsa", "bara": "Bara",
    "dhanusha": "Dhanusha", "dhanusa": "Dhanusha", "mahottari": "Mahottari", "sarlahi": "Sarlahi", "rautahat": "Rautahat",
    "saptari": "Saptari", "siraha": "Siraha", "kanchanpur": "Kanchanpur", "bardiya": "Bardiya", "kapilvastu": "Kapilvastu",
    "kapilbastu": "Kapilvastu", "nawalparasi": "Nawalparasi", "nawalpur": "Nawalparasi", "tanahun": "Tanahun",
    "tanahu": "Tanahun", "dhading": "Dhading", "sindhupalchok": "Sindhupalchok", "sindhupalchowk": "Sindhupalchok",
    "dolakha": "Dolakha", "palpa": "Palpa", "syangja": "Syangja", "gorkha": "Gorkha", "lamjung": "Lamjung",
    "ilam": "Ilam", "parbat": "Parbat", "baglung": "Baglung", "myagdi": "Myagdi", "rasuwa": "Rasuwa",
    "sindhuli": "Sindhuli", "udayapur": "Udayapur", "dhankuta": "Dhankuta",
}

# Town / municipality -> (city label, district). These are the places people price by
# outside the Kathmandu Valley; a listing's "city" is the first of these found.
TOWNS = {
    # Kaski
    "pokhara": ("Pokhara", "Kaski"), "lekhnath": ("Pokhara", "Kaski"), "lakeside": ("Pokhara", "Kaski"),
    "hemja": ("Pokhara", "Kaski"), "bijayapur": ("Pokhara", "Kaski"), "chipledhunga": ("Pokhara", "Kaski"),
    "prithvi chowk": ("Pokhara", "Kaski"), "birauta": ("Pokhara", "Kaski"), "begnas": ("Pokhara", "Kaski"),
    # Chitwan
    "bharatpur": ("Bharatpur", "Chitwan"), "narayangarh": ("Bharatpur", "Chitwan"), "narayangadh": ("Bharatpur", "Chitwan"),
    "ratnanagar": ("Ratnanagar", "Chitwan"), "tandi": ("Ratnanagar", "Chitwan"), "sauraha": ("Ratnanagar", "Chitwan"),
    "khairahani": ("Khairahani", "Chitwan"), "kalika": ("Kalika", "Chitwan"), "rapti": ("Rapti", "Chitwan"),
    "gitanagar": ("Bharatpur", "Chitwan"), "parsa chitwan": ("Khairahani", "Chitwan"),
    # Rupandehi
    "butwal": ("Butwal", "Rupandehi"), "tilottama": ("Butwal", "Rupandehi"), "manigram": ("Butwal", "Rupandehi"),
    "bhairahawa": ("Bhairahawa", "Rupandehi"), "siddharthanagar": ("Bhairahawa", "Rupandehi"),
    "devdaha": ("Devdaha", "Rupandehi"), "sainamaina": ("Sainamaina", "Rupandehi"), "lumbini": ("Lumbini", "Rupandehi"),
    # Morang / Sunsari
    "biratnagar": ("Biratnagar", "Morang"), "urlabari": ("Urlabari", "Morang"), "pathari": ("Pathari", "Morang"),
    "belbari": ("Belbari", "Morang"), "letang": ("Letang", "Morang"), "rangeli": ("Rangeli", "Morang"),
    "sundarharaicha": ("Sundarharaicha", "Morang"), "ratuwamai": ("Ratuwamai", "Morang"),
    "itahari": ("Itahari", "Sunsari"), "dharan": ("Dharan", "Sunsari"), "inaruwa": ("Inaruwa", "Sunsari"),
    "duhabi": ("Duhabi", "Sunsari"),
    # Jhapa
    "birtamod": ("Birtamod", "Jhapa"), "birtamode": ("Birtamod", "Jhapa"), "damak": ("Damak", "Jhapa"),
    "mechinagar": ("Mechinagar", "Jhapa"), "kakarvitta": ("Mechinagar", "Jhapa"), "kakarbhitta": ("Mechinagar", "Jhapa"),
    "bhadrapur": ("Bhadrapur", "Jhapa"), "arjundhara": ("Arjundhara", "Jhapa"), "gauradaha": ("Gauradaha", "Jhapa"),
    "chandragadi": ("Bhadrapur", "Jhapa"), "surunga": ("Kankai", "Jhapa"),
    # Makwanpur, Kavre, Nuwakot, Dhading
    "hetauda": ("Hetauda", "Makwanpur"), "manahari": ("Manahari", "Makwanpur"),
    "banepa": ("Banepa", "Kavrepalanchok"), "dhulikhel": ("Dhulikhel", "Kavrepalanchok"), "panauti": ("Panauti", "Kavrepalanchok"),
    "panchkhal": ("Panchkhal", "Kavrepalanchok"), "namobuddha": ("Namobuddha", "Kavrepalanchok"),
    "bidur": ("Bidur", "Nuwakot"), "trishuli": ("Bidur", "Nuwakot"), "dhadingbesi": ("Dhading Besi", "Dhading"),
    "nilkantha": ("Dhading Besi", "Dhading"), "malekhu": ("Malekhu", "Dhading"),
    # West / far west
    "nepalgunj": ("Nepalgunj", "Banke"), "kohalpur": ("Kohalpur", "Banke"), "dhangadhi": ("Dhangadhi", "Kailali"),
    "tikapur": ("Tikapur", "Kailali"), "lamki": ("Lamki", "Kailali"), "mahendranagar": ("Mahendranagar", "Kanchanpur"),
    "bhimdatta": ("Mahendranagar", "Kanchanpur"), "ghorahi": ("Ghorahi", "Dang"), "tulsipur": ("Tulsipur", "Dang"),
    "lamahi": ("Lamahi", "Dang"), "birendranagar": ("Birendranagar", "Surkhet"), "gulariya": ("Gulariya", "Bardiya"),
    "taulihawa": ("Kapilvastu", "Kapilvastu"), "tansen": ("Tansen", "Palpa"), "waling": ("Waling", "Syangja"),
    "putalibazar": ("Putalibazar", "Syangja"), "damauli": ("Damauli", "Tanahun"), "bandipur": ("Bandipur", "Tanahun"),
    "besisahar": ("Besisahar", "Lamjung"), "beni": ("Beni", "Myagdi"), "kushma": ("Kushma", "Parbat"),
    # Madhesh
    "birgunj": ("Birgunj", "Parsa"), "simara": ("Simara", "Bara"), "kalaiya": ("Kalaiya", "Bara"),
    "janakpur": ("Janakpur", "Dhanusha"), "bardibas": ("Bardibas", "Mahottari"), "lalbandi": ("Lalbandi", "Sarlahi"),
    "rajbiraj": ("Rajbiraj", "Saptari"), "lahan": ("Lahan", "Siraha"), "gaur": ("Gaur", "Rautahat"),
    # Nawalparasi (Nawalpur / Parasi)
    "kawasoti": ("Kawasoti", "Nawalparasi"), "gaindakot": ("Gaindakot", "Nawalparasi"), "gaidakot": ("Gaindakot", "Nawalparasi"),
    "devchuli": ("Devchuli", "Nawalparasi"), "madhyabindu": ("Madhyabindu", "Nawalparasi"), "bardaghat": ("Bardaghat", "Nawalparasi"),
    "sunwal": ("Sunwal", "Nawalparasi"), "ramgram": ("Ramgram", "Nawalparasi"),
    # Others
    "charikot": ("Charikot", "Dolakha"), "chautara": ("Chautara", "Sindhupalchok"), "melamchi": ("Melamchi", "Sindhupalchok"),
    "ilam bazar": ("Ilam", "Ilam"), "dhankuta bazar": ("Dhankuta", "Dhankuta"), "triyuga": ("Gaighat", "Udayapur"),
    "gaighat": ("Gaighat", "Udayapur"), "sindhulimadi": ("Sindhuli", "Sindhuli"),
}

# Kathmandu Valley localities whose district is unambiguous. Used when an address names
# only the locality ("Tikathali, Imadol"). Learned localities from structured addresses
# extend this at cleaning time.
VALLEY = {
    "Kathmandu": "budhanilkantha budanilkantha tokha gongabu samakhusi dhapasi basundhara maharajgunj baluwatar lazimpat naxal "
                 "thamel kalanki kalimati teku tripureshwor baneshwor koteshwor tinkune sinamangal battisputali chabahil bouddha "
                 "jorpati gokarna kapan mulpani sankhu thali sundarijal kirtipur chandragiri thankot naikap sitapaila swayambhu "
                 "balaju dallu nagarjun ramkot kuleshwor balkhu dakshinkali pharping chapali bansbari sukedhara golfutar "
                 "kageshwori manohara tarakeshwor shankharapur bhangal grande dhumbarahi mandikatar mahadevsthan bishalnagar "
                 "chandol hattigauda pepsicola sanobharyang raniban gothatar tahachal kalopul gyaneshwor",
    "Lalitpur": "imadol tikathali godawari lubhu bhaisepati sanepa jhamsikhel jawalakhel satdobato hattiban dhapakhel chapagaun "
                "harisiddhi khumaltar kusunti ekantakuna nakhipot sunakothi thecho bungamati gwarko balkumari pulchowk kupondole "
                "bakhundol lagankhel mahalaxmi siddhipur thaiba bajrabarahi nakkhu dhobighat bhanimandal tikabhairab",
    "Bhaktapur": "thimi madhyapur suryabinayak changunarayan sallaghari kausaltar lokanthali gatthaghar nagarkot katunje "
                 "jagati duwakot sipadol balkot sirutar dadhikot nagadesh bode",
}
VALLEY_LOC = {w: d for d, ws in VALLEY.items() for w in ws.split()}

# Districts where land is measured in bigha-kattha-dhur.
TERAI = {"Chitwan", "Rupandehi", "Morang", "Sunsari", "Jhapa", "Kailali", "Banke", "Makwanpur", "Parsa", "Bara",
         "Dhanusha", "Mahottari", "Sarlahi", "Rautahat", "Saptari", "Siraha", "Kanchanpur", "Bardiya", "Kapilvastu",
         "Nawalparasi", "Dang", "Udayapur"}

STOP = r"\b(municipality|municipal|nagarpalika|mahanagarpalika|sub-?metropolitan|metropolitan|metro|city|ward|chowk|marga|road|tole|height|heights|planning|colony|area|near|nepal)\b"

def norm_locality(s):
    s = re.sub(r"[-\s]*\d+\b", "", s or "").strip(" ,.-")
    s = re.sub(STOP, "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" ,.-").title() or None

def _district_word(w):
    """District for one word, tolerating small misspellings ('Kathamndu', 'Moramg')."""
    import difflib
    w = re.sub(r"[^a-z]", "", (w or "").lower())
    if w in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[w]
    if len(w) >= 5:
        m = difflib.get_close_matches(w, [k for k in DISTRICT_ALIASES if len(k) >= 5], n=1, cutoff=0.83)
        if m:
            return DISTRICT_ALIASES[m[0]]
    return None

def _strip_district_words(loc):
    """'Sitapaila Kathmandu' -> 'Sitapaila'."""
    ws = (loc or "").split()
    while len(ws) > 1 and _district_word(ws[-1]):
        ws.pop()
    return " ".join(ws) or None

def _key(s):
    return re.sub(r"[^a-z ]", "", (s or "").lower()).strip()

def find_town(text):
    """First town in the text (longest names first), as (city, district) or None."""
    t = " " + re.sub(r"[^a-z]+", " ", (text or "").lower()) + " "
    hits = [(t.find(" " + k + " "), -len(k), k) for k in TOWNS if " " + k + " " in t]
    return TOWNS[min(hits)[2]] if hits else None

def find_district(text):
    t = re.findall(r"[a-z]+", (text or "").lower())
    for w in reversed(t):
        if _district_word(w):
            return _district_word(w)
    return None

def district_from_words(text, known=None):
    """Last-resort district from any well-known locality word in the text."""
    known = known or {}
    for w in reversed(re.findall(r"[a-z]+", (text or "").lower())):
        d = VALLEY_LOC.get(w) or known.get(w)
        if d:
            return d
    return None

def split_address(addr, title=None, known=None):
    """('VS Colony, Pepsicola, Kathmandu') -> locality 'Pepsicola', city None, district 'Kathmandu'.
    `known` maps a lower-case locality to its district (learned from structured addresses)."""
    known = known or {}
    parts = [p.strip() for p in re.split(r"[,|]", addr or "") if p.strip()]
    district = None
    for p in reversed(parts):
        d = _district_word(p.split("-")[0])
        if d:
            district = d; parts.remove(p); break
    if not district and parts:
        last = parts[-1].split()
        if len(last) > 1 and _district_word(last[-1]):
            district = _district_word(last[-1])
    town = find_town(addr) or find_town(title)
    district = district or (town[1] if town else None) or find_district(title)
    locs = [_strip_district_words(norm_locality(p)) for p in parts]
    locs = [l for l in locs if l and not _district_word(l)]
    locality = locs[-1] if locs else None
    if not district and locality:
        district = VALLEY_LOC.get(_key(locality).replace(" ", "")) or known.get(_key(locality))
    if not district:
        for l in reversed(locs):
            d = VALLEY_LOC.get(_key(l).replace(" ", "")) or known.get(_key(l))
            if d:
                district = d; break
    city = town[0] if town and town[1] == district else None
    if district in ("Kathmandu", "Lalitpur", "Bhaktapur"):
        city = None
    return locality, city, district

def locality_from_text(text, vocab):
    """Free-text titles ("4.5 aana house sale tokha panchetar Kathmandu"): the longest
    known locality name that appears in the text. `vocab` maps lower-case name -> (Name, district)."""
    t = " " + re.sub(r"[^a-z]+", " ", (text or "").lower()) + " "
    best = None
    for k, v in vocab.items():
        if len(k) >= 4 and " " + k + " " in t and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else (None, None)
