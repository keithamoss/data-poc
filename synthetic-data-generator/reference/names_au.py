"""
Reference name/geography pools for the synthetic population generator.

Hand-authored (no Faker/pip access in this environment - see README). Skewed
by rank so the generated population has a realistic name-frequency curve
(a handful of names are common, a long tail is rare) rather than every name
being equally likely, which is what makes bulk-generated data look synthetic
at a glance.

Surnames and suburbs draw on the real cultural and geographic mix of Western
Australia (Anglo-Celtic, Indigenous Australian, Southern/Eastern European,
Vietnamese, Chinese, Indian, Filipino) so the generated population doesn't
default to a monoculture. Suburb names are real, public WA geography - no
person-level data is attached to them beyond what this generator invents.
"""
import numpy as np

def zipf_weights(n, s=1.07):
    ranks = np.arange(1, n + 1)
    w = 1.0 / np.power(ranks, s)
    return w / w.sum()

GIVEN_NAMES_MALE = [
    "Oliver","William","Jack","Noah","Thomas","James","Lucas","Henry","Leo","Ethan",
    "Charlie","Alexander","Mason","Michael","Elijah","Daniel","Cooper","Isaac","Levi","Ryan",
    "Jacob","Hunter","Hudson","Harrison","Archie","Max","Samuel","David","Sebastian","Nathan",
    "Xavier","Joshua","Liam","Aiden","Connor","Logan","Blake","Riley","Zac","Toby",
    "Angus","Bailey","Callum","Dominic","Felix","Gabriel","Harvey","Ivan","Jayden","Kai",
    "Minh","Duc","Anh","Wei","Jian","Hiro","Kenji","Arjun","Raj","Vikram",
    "Tane","Kepa","Waka","Dwayne","Trent","Brayden","Cody","Corey","Dean","Errol",
]
GIVEN_NAMES_FEMALE = [
    "Charlotte","Olivia","Amelia","Isla","Mia","Ava","Grace","Ella","Sophie","Chloe",
    "Ruby","Willow","Zoe","Lily","Aria","Matilda","Ivy","Layla","Harper","Evie",
    "Emily","Georgia","Hannah","Lucy","Millie","Poppy","Scarlett","Alice","Freya","Maya",
    "Isabella","Sienna","Piper","Eleanor","Violet","Stella","Audrey","Josephine","Rosie","Frankie",
    "Thi","Linh","Mai","Xin","Yan","Yui","Sakura","Priya","Anita","Divya",
    "Aroha","Manaia","Kiri","Shanae","Chelsea","Paige","Kayla","Renee","Bridget","Fiona",
]
GIVEN_NAMES_UNISEX = [
    "Jordan","Taylor","Morgan","Riley","Casey","Charlie","Alex","Sam","Jamie","Rowan",
    "Kai","Ash","Remy","Quinn","Reese",
]

FAMILY_NAMES = [
    # Anglo-Celtic (majority share, reflecting WA census composition)
    "Smith","Jones","Williams","Brown","Wilson","Taylor","Johnson","White","Martin","Anderson",
    "Thompson","Nguyen","Thomas","Walker","Harris","Lee","Ryan","Robinson","Kelly","King",
    "Davies","Wright","Evans","Roberts","Green","Hall","Wood","Jackson","Clarke","Patel",
    "Cook","Mitchell","Morgan","Bell","Shaw","Reid","Murphy","Cox","Richardson","Watson",
    "Hughes","Edwards","Turner","Phillips","Campbell","Parker","Stevens","Baker","Adams","Collins",
    # Southern / Eastern European
    "Rossi","Marino","Kovac","Novak","Petrov","Ivanov","Kowalski","Nowak","Popescu","Dimitriou",
    # Vietnamese / Chinese / broader East & South Asian (large WA communities)
    "Tran","Le","Pham","Vo","Huynh","Ho","Wong","Chen","Zhang","Liu",
    "Wang","Tan","Lim","Singh","Kaur","Sharma","Khan","Ahmed","Hassan","Rahman",
    # Filipino / Pacific
    "Santos","Reyes","Cruz","Bautista","Fonoti","Tuilagi","Faleolo","Havili",
    # Indigenous Australian surnames represented in WA communities
    "Hayden","Ryder","Yarran","Nannup","Bennell","Councillor","Wongawol","Riley","Dann","Garlett",
]

# WA suburb / town names - real, public geography, no person-level data attached.
SUBURBS = [
    ("Fremantle","6160"),("Subiaco","6008"),("Joondalup","6027"),("Rockingham","6168"),
    ("Mandurah","6210"),("Midland","6056"),("Armadale","6112"),("Cannington","6107"),
    ("Morley","6062"),("Cockburn Central","6164"),("Scarborough","6019"),("Victoria Park","6100"),
    ("Bunbury","6230"),("Albany","6330"),("Geraldton","6530"),("Kalgoorlie","6430"),
    ("Broome","6725"),("Karratha","6714"),("Port Hedland","6721"),("Busselton","6280"),
    ("Northam","6401"),("Narrogin","6312"),("Esperance","6450"),("Collie","6225"),
    ("Mount Lawley","6050"),("Leederville","6007"),("Wembley","6014"),("Innaloo","6018"),
    ("Success","6164"),("Baldivis","6171"),("Ellenbrook","6069"),("Butler","6036"),
    ("Balga","6061"),("Girrawheen","6064"),("Maddington","6109"),
    ("Gosnells","6110"),("Kwinana","6167"),("Hamilton Hill","6163"),("Beaconsfield","6162"),
    ("South Perth","6151"),("Bentley","6102"),("Willetton","6155"),("Riverton","6148"),
    ("Karrinyup","6018"),("Currambine","6028"),("Clarkson","6030"),("Yanchep","6035"),
    ("Byford","6122"),("Waroona","6215"),("Manjimup","6258"),("Margaret River","6285"),
]

STREET_NAME_STEMS = [
    "Wattle","Banksia","Marri","Jarrah","Karri","Tuart","Grevillea","Kestrel","Osprey","Curlew",
    "Skyline","Ridgeview","Harbourside","Endeavour","Discovery","Settlers","Pioneer","Federation",
    "Emerald","Amberley","Hartley","Rosewood","Fairview","Carrington","Sussex","Grosvenor",
    "Beachcomber","Lakeview","Riverbend","Cormorant","Silverleaf","Cinnamon","Saltbush","Spinifex",
]
STREET_TYPES = ["Street","Road","Avenue","Way","Crescent","Court","Place","Drive","Loop","Terrace"]

def build_name_pools():
    return {
        "male": (np.array(GIVEN_NAMES_MALE), zipf_weights(len(GIVEN_NAMES_MALE))),
        "female": (np.array(GIVEN_NAMES_FEMALE), zipf_weights(len(GIVEN_NAMES_FEMALE))),
        "unisex": (np.array(GIVEN_NAMES_UNISEX), zipf_weights(len(GIVEN_NAMES_UNISEX))),
        "family": (np.array(FAMILY_NAMES), zipf_weights(len(FAMILY_NAMES))),
    }

def build_geo_pools():
    suburb_names = np.array([s[0] for s in SUBURBS])
    postcodes = np.array([s[1] for s in SUBURBS])
    return suburb_names, postcodes, np.array(STREET_NAME_STEMS), np.array(STREET_TYPES)
