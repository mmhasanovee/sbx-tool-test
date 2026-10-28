"""Generates ~533k synthetic records for the SBX test org and loads them with Bulk API 2.0.

Run from the project root:
    python -I scripts/load_data.py generate              # writes data/csv/*.csv (deterministic, same output every run)
    python -I scripts/load_data.py load SBX-TOOL-PROD    # loads the CSVs; steps already in data/load_state.json are skipped
    python -I scripts/load_data.py verify SBX-TOOL-PROD  # compares org record counts with the generated CSVs

The CSVs hold no org Ids. Lookups use Legacy_Id__c external Ids, and values that need an Id at
load time are tokens resolved against the target org: @RT:<Object>.<DeveloperName>, @QUEUE:<DeveloperName>,
@OWNER:<n> (n-th active System Administrator), @PBE:<product legacy id> (standard price book entry)
and @REC:<legacy id> (Account, Contact, Lead, Opportunity or Case). The same files can seed a sandbox.
"""
import csv
import datetime as dt
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SEED = 2026
TODAY = dt.date(2026, 10, 28)
DATA = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
CSV_DIR = os.path.join(DATA, "csv")
FAILED_DIR = os.path.join(DATA, "failed")
STATE_FILE = os.path.join(DATA, "load_state.json")

# ---------------------------------------------------------------- reference values

REGIONS = [  # country, ISO code, cities, weight
    ("Kuwait", "KW", ["Kuwait City", "Hawalli", "Salmiya"], 14), ("Saudi Arabia", "SA", ["Riyadh", "Jeddah", "Dammam"], 12),
    ("United Arab Emirates", "AE", ["Dubai", "Abu Dhabi", "Sharjah"], 12), ("Qatar", "QA", ["Doha", "Al Wakrah"], 6),
    ("Bahrain", "BH", ["Manama", "Muharraq"], 4), ("Oman", "OM", ["Muscat", "Sohar"], 4), ("Egypt", "EG", ["Cairo", "Alexandria"], 5),
    ("Jordan", "JO", ["Amman", "Irbid"], 3), ("United Kingdom", "GB", ["London", "Manchester", "Leeds"], 7),
    ("Germany", "DE", ["Berlin", "Munich", "Hamburg"], 5), ("France", "FR", ["Paris", "Lyon"], 4), ("Netherlands", "NL", ["Amsterdam", "Rotterdam"], 3),
    ("United States", "US", ["New York", "Chicago", "Austin", "Seattle"], 8), ("Canada", "CA", ["Toronto", "Vancouver"], 3),
    ("India", "IN", ["Mumbai", "Bengaluru", "Delhi"], 4), ("Singapore", "SG", ["Singapore"], 2), ("Australia", "AU", ["Sydney", "Melbourne"], 2),
    ("Japan", "JP", ["Tokyo", "Osaka"], 1), ("Brazil", "BR", ["Sao Paulo", "Rio de Janeiro"], 1), ("South Africa", "ZA", ["Johannesburg", "Cape Town"], 1),
]
CURRENCIES = {"KWD": 3.25, "SAR": 0.267, "AED": 0.272, "QAR": 0.275, "BHD": 2.65, "OMR": 2.6, "EGP": 0.021, "JOD": 1.41, "GBP": 1.27, "EUR": 1.08}
FIRST = ["Aisha", "Omar", "Lina", "Yousef", "Sara", "Karim", "Noor", "Hadi", "Maya", "Tariq", "Rania", "Ali", "Dana", "Fahad", "Huda",
         "James", "Emma", "Liam", "Olivia", "Noah", "Sophia", "Lucas", "Mia", "Ethan", "Chloe", "Arjun", "Priya", "Rohan", "Ananya",
         "Kenji", "Yuki", "Mateo", "Lucia", "Hans", "Greta", "Pierre", "Camille", "Daan", "Sanne", "Thabo", "Zanele", "Wei", "Mei"]
LAST = ["Haddad", "Rahman", "Saleh", "Nasser", "Khalil", "Farouk", "Aziz", "Mansour", "Qasim", "Darwish", "Hamdan", "Jaber", "Al-Sabah",
        "Al-Mutairi", "Smith", "Johnson", "Brown", "Taylor", "Wilson", "Davies", "Evans", "Patel", "Sharma", "Iyer", "Tanaka", "Sato",
        "Garcia", "Silva", "Muller", "Schmidt", "Dubois", "Martin", "de Vries", "Jansen", "Nkosi", "Dlamini", "Chen", "Wong", "Kumar"]
CO_A = ["Gulf", "Al Noor", "Atlas", "Blue Harbor", "Summit", "Crescent", "Falcon", "Pearl", "Oasis", "Northwind", "Silverline", "Desert Rose",
        "Horizon", "Keystone", "Meridian", "Sapphire", "Cedar", "Ironbridge", "Golden Sands", "Evergreen", "Pinnacle", "Vertex", "Harbor Point"]
CO_B = ["Trading", "Logistics", "Energy", "Engineering", "Health", "Systems", "Foods", "Construction", "Retail", "Technologies", "Marine",
        "Petrochemicals", "Pharma", "Telecom", "Consulting", "Industries", "Facilities", "Capital", "Motors", "Contracting"]
CO_C = ["Co", "LLC", "Group", "Holdings", "Ltd", "International", "WLL", "Inc", "KSC", "Partners"]
INDUSTRY = ["Agriculture", "Apparel", "Banking", "Biotechnology", "Chemicals", "Communications", "Construction", "Consulting", "Education",
            "Electronics", "Energy", "Engineering", "Entertainment", "Environmental", "Finance", "Food & Beverage", "Government", "Healthcare",
            "Hospitality", "Insurance", "Machinery", "Manufacturing", "Media", "Not For Profit", "Recreation", "Retail", "Shipping",
            "Technology", "Telecommunications", "Transportation", "Utilities", "Other"]
LEAD_SOURCE = ["Advertisement", "Employee Referral", "External Referral", "Partner", "Public Relations", "Seminar - Internal",
               "Seminar - Partner", "Trade Show", "Web", "Word of mouth", "Other"]
TITLES = ["CEO", "CFO", "COO", "IT Director", "Procurement Manager", "Operations Manager", "Finance Manager", "Project Manager",
          "Facilities Manager", "Sales Director", "HR Manager", "Engineer", "Analyst", "Office Manager", "Buyer"]
DEPARTMENTS = ["Executive", "Finance", "IT", "Operations", "Procurement", "Sales", "HR", "Engineering", "Facilities"]
PRODUCT_ADJ = ["Industrial", "Smart", "Compact", "Heavy-Duty", "Portable", "Premium", "Eco", "Digital", "Modular", "Pro"]
PRODUCT_NOUN = ["Pump", "Generator", "Sensor", "Controller", "Valve", "Compressor", "Router", "Server", "Chiller", "Meter", "Filter",
                "Drive", "Panel", "Gateway", "Scanner", "Licence", "Support Pack", "Training Day", "Installation Service", "Cable Kit"]
SKILL_BASE = ["Salesforce Administration", "Apex Development", "Lightning Web Components", "Flow Automation", "Data Migration",
              "Integration Design", "Project Management", "Business Analysis", "Electrical Installation", "HVAC Maintenance",
              "Network Engineering", "Cloud Architecture", "Quality Inspection", "Health and Safety", "Contract Negotiation",
              "Customer Service", "Technical Writing", "Arabic Translation", "Financial Reporting", "Procurement",
              "Welding", "Plumbing", "Fire Safety", "Change Management", "Data Analysis"]
SKILL_LEVEL = ["", " II", " Advanced", " Certified"]
SKILL_CATEGORY = ["Technical", "Functional", "Soft Skill", "Certification"]
CASE_REASON = ["User didn't attend training", "Complex functionality", "Existing problem", "Instructions not clear", "New problem"]
CASE_SUBJECT = {"Support": ["Unit not starting", "Error code on display", "Login issue on portal", "Request for maintenance visit",
                            "Spare part needed", "Software update failed", "Unexpected noise from unit"],
                "Complaint": ["Late delivery", "Billing discrepancy", "Technician did not arrive", "Damaged on arrival", "Poor response time"],
                "Inspection": ["Annual safety inspection", "Post-installation inspection", "Warranty inspection", "Compliance audit visit"]}
OPP_OPEN = ["Prospecting", "Qualification", "Needs Analysis", "Value Proposition", "Id. Decision Makers", "Perception Analysis",
            "Proposal/Price Quote", "Negotiation/Review"]
OCR_ROLE = ["Business User", "Decision Maker", "Economic Buyer", "Economic Decision Maker", "Evaluator", "Executive Sponsor",
            "Influencer", "Technical Buyer", "Other"]
SUPPLIER_SUB = {"Materials": ["Steel", "Timber"], "Services": ["Consulting", "Maintenance"], "Logistics": ["Freight", "Warehousing"],
                "Software": ["Licences", "Cloud"]}
CHECKLIST = ["Visual condition", "Electrical connections", "Earthing and bonding", "Pressure test", "Safety labels", "Emergency stop",
             "Firmware version", "Filter condition", "Noise and vibration", "Documentation on site"]
ENDPOINTS = [("Outbound", "callout:ERP_API/cases"), ("Outbound", "callout:ERP_API/accounts"), ("Outbound", "callout:Payment_Gateway/v1/charges"),
             ("Inbound", "/services/apexrest/erp/orders"), ("Inbound", "/services/apexrest/payments/webhook")]
PHASES = ["Discovery", "Design", "Build", "Test", "Deploy", "Handover"]
WP_TASKS = ["Site survey", "Requirements workshop", "Solution design", "Procurement", "Installation", "Configuration", "Data migration",
            "User training", "Testing", "Go-live support", "Documentation"]

COUNTS = dict(region=20, tax_rate=50, currency_rate=200, skill=100, product=500, account=10000, contact=30000, lead=15000,
              opportunity=25000, opportunity_line=60000, contact_role=20000, campaign=100, campaign_member=20000, case=30000,
              case_comment=25000, customer_feedback=5000, support_plan=3000, task=40000, event=15000, contract=3000, order=8000,
              order_item=20000, asset=10000, project=3000, work_package=20000, time_entry=40000, invoice=8000, invoice_line=25000,
              payment=8000, supplier=500, supplier_contact=1500, project_supplier=4000, contact_skill=20000, inspection=5000,
              approval_log=5000, document_request=3000, integration_log=25000, case_parent=2000, project_parent=300)


def lid(prefix, i, width=5):
    return f"{prefix}-{i:0{width}d}"


def day(offset):
    return (TODAY + dt.timedelta(days=offset)).isoformat()


def stamp(rng, offset):
    t = dt.datetime.combine(TODAY, dt.time()) + dt.timedelta(days=offset, minutes=rng.randrange(7 * 60, 18 * 60, 15))
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def pick(rng, weighted):
    return rng.choices(list(weighted), weights=list(weighted.values()))[0]


def save(name, header, rows):
    with open(os.path.join(CSV_DIR, name + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name}: {len(rows):,}", flush=True)


# ---------------------------------------------------------------- generation

def generate():
    rng = random.Random(SEED)
    os.makedirs(CSV_DIR, exist_ok=True)
    print("Generating CSVs in", CSV_DIR, flush=True)
    region_w = [r[3] for r in REGIONS]

    # Reference data
    save("region", ["Legacy_Id__c", "Name", "Code__c", "Country__c"],
         [[lid("REG", i + 1, 3), r[0], r[1], r[0]] for i, r in enumerate(REGIONS)])
    tax_rows = []
    for i in range(1, COUNTS["tax_rate"] + 1):
        country, code = REGIONS[(i - 1) % len(REGIONS)][:2]
        rate = rng.choice([0, 5, 7.5, 10, 15, 19, 20])
        tax_rows.append([lid("TAX", i, 3), f"{code} {'Standard' if i <= 20 else 'Reduced' if i <= 40 else 'Special'} {rate}%", rate, country,
                         day(-rng.randrange(30, 2000))])
    save("tax_rate", ["Legacy_Id__c", "Name", "Rate__c", "Country__c", "Effective_From__c"], tax_rows)
    cur_rows, n = [], 0
    for code, base in CURRENCIES.items():
        for m in range(20):
            n += 1
            d = day(-30 * m)
            cur_rows.append([lid("CUR", n, 3), f"{code} {d}", code, round(base * rng.uniform(0.97, 1.03), 6), d])
    save("currency_rate", ["Legacy_Id__c", "Name", "Currency_Code__c", "Rate__c", "Rate_Date__c"], cur_rows)
    save("skill", ["Legacy_Id__c", "Name", "Category__c"],
         [[lid("SKL", i * 4 + j + 1, 3), SKILL_BASE[i] + SKILL_LEVEL[j], "Certification" if j == 3 else rng.choice(SKILL_CATEGORY[:3])]
          for i in range(len(SKILL_BASE)) for j in range(4)])
    price = {}
    prod_rows = []
    for i in range(1, COUNTS["product"] + 1):
        noun = PRODUCT_NOUN[(i - 1) % len(PRODUCT_NOUN)]
        name = f"{PRODUCT_ADJ[(i - 1) // len(PRODUCT_NOUN) % len(PRODUCT_ADJ)]} {noun} {100 + i}"
        price[i] = round(rng.choice([25, 50, 120, 300, 750, 1500, 4200, 9800]) * rng.uniform(0.8, 1.3), 2)
        prod_rows.append([lid("PRD", i), name, f"P{i:05d}", "true", f"{name}, catalogue item {i}"])
    save("product", ["Legacy_Id__c", "Name", "ProductCode", "IsActive", "Description"], prod_rows)
    save("pricebook", ["Legacy_Id__c", "Name", "IsActive", "Description"],
         [["PB-PARTNER", "SBX Partner Price Book", "true", "Partner pricing, 15% below list"],
          ["PB-ENT", "SBX Enterprise Price Book", "true", "Enterprise pricing, 10% below list"]])
    save("pbe_std", ["Pricebook2.Legacy_Id__c", "Product2.Legacy_Id__c", "UnitPrice", "IsActive", "UseStandardPrice"],
         [["PB-STD", lid("PRD", i), price[i], "true", "false"] for i in price])
    save("pbe_custom", ["Pricebook2.Legacy_Id__c", "Product2.Legacy_Id__c", "UnitPrice", "IsActive", "UseStandardPrice"],
         [[pb, lid("PRD", i), round(price[i] * f, 2), "true", "false"] for pb, f in (("PB-PARTNER", 0.85), ("PB-ENT", 0.9)) for i in price])

    camp_rows = []
    for i in range(1, COUNTS["campaign"] + 1):
        start = -rng.randrange(-90, 700)
        status = "Planned" if start > 0 else rng.choice(["In Progress", "Completed", "Completed", "Aborted"])
        typ = rng.choice(["Advertisement", "Email", "Telemarketing", "Banner Ads", "Seminar / Conference", "Public Relations", "Partners",
                          "Referral Program", "Other"])
        camp_rows.append([lid("CMP", i, 3), f"{day(start)[:4]} {rng.choice(PRODUCT_NOUN)} {typ} {i}", typ, status, day(start), day(start + 60),
                          "true" if status in ("Planned", "In Progress") else "false", rng.randrange(1000, 50000, 500)])
    save("campaign", ["Legacy_Id__c", "Name", "Type", "Status", "StartDate", "EndDate", "IsActive", "BudgetedCost"], camp_rows)

    # Accounts: 1,000 roots, 3,000 subsidiaries, 6,000 branches
    acc = [None]
    acc_rows, hier_rows = [], []
    for i in range(1, COUNTS["account"] + 1):
        if i <= 1000:
            parent, level = None, 1
            root = f"{rng.choice(CO_A)} {rng.choice(CO_B)} {rng.choice(CO_C)}"
            rt = pick(rng, {"Customer": 80, "Partner": 12, "Supplier": 8})
            reg = rng.choices(range(len(REGIONS)), weights=region_w)[0]
            owner = rng.randrange(2)
        else:
            parent = rng.randint(1, 1000) if i <= 4000 else rng.randint(1001, 4000)
            level = 2 if i <= 4000 else 3
            p = acc[parent]
            root, rt, owner = p["root"], p["rt"], p["owner"]
            reg = p["reg"] if rng.random() < 0.7 else rng.choices(range(len(REGIONS)), weights=region_w)[0]
        country, code, cities = REGIONS[reg][:3]
        city = rng.choice(cities)
        name = root if level == 1 else f"{root} - {city}" if level == 2 else f"{root} - {city} {rng.choice(['Operations', 'Sales', 'Service', 'Projects'])}"
        acc.append(dict(root=root, rt=rt, owner=owner, reg=reg, country=country, city=city, name=name, parent=parent, level=level))
        typ = {"Customer": rng.choice(["Customer", "Customer", "Prospect"]), "Partner": rng.choice(["Partner", "Reseller", "Integrator"]),
               "Supplier": "Other"}[rt]
        employees = rng.randrange(10, 50000) // level
        acc_rows.append([lid("ACC", i), name, f"@RT:Account.{rt}", typ, rng.choice(INDUSTRY), f"{rng.randrange(1, 400)} {rng.choice(LAST)} Street",
                         city, f"{rng.randrange(10000, 99999)}", country, f"+{rng.randrange(1, 999)} {rng.randrange(2000000, 9999999)}",
                         f"https://www.{root.split()[0].lower()}{i}.example.com", employees * rng.randrange(40000, 250000), employees,
                         lid("REG", reg + 1, 3), pick(rng, {"Strategic": 10, "Key": 25, "Standard": 65}), f"@OWNER:{owner}",
                         f"Level {level} account in the {root} group"])
    save("account", ["Legacy_Id__c", "Name", "RecordTypeId", "Type", "Industry", "BillingStreet", "BillingCity", "BillingPostalCode",
                     "BillingCountry", "Phone", "Website", "AnnualRevenue", "NumberOfEmployees", "Region__r.Legacy_Id__c",
                     "Customer_Tier__c", "OwnerId", "Description"], acc_rows)
    del acc_rows
    sales_accounts = [i for i in range(1, len(acc)) if acc[i]["rt"] != "Supplier"]
    supplier_accounts = [i for i in range(1, len(acc)) if acc[i]["rt"] == "Supplier"]

    # Contacts: every account gets one, the rest weighted towards group roots
    per_acc = [0] + [1] * COUNTS["account"]
    weights = [3 if a["level"] == 1 else 2 if a["level"] == 2 else 1 for a in acc[1:]]
    for a in rng.choices(range(1, len(acc)), weights=weights, k=COUNTS["contact"] - COUNTS["account"]):
        per_acc[a] += 1
    acc_contacts = [[] for _ in acc]
    con_acc = [0]
    con_rows = []
    c = 0
    for a in range(1, len(acc)):
        for _ in range(per_acc[a]):
            c += 1
            first, last = rng.choice(FIRST), rng.choice(LAST)
            acc_contacts[a].append(c)
            con_acc.append(a)
            has_phone = rng.random() < 0.9
            con_rows.append([lid("CON", c), first, last, f"{first}.{last.replace(' ', '')}.{c}@example.com".lower(),
                             f"+{rng.randrange(1, 999)} {rng.randrange(2000000, 9999999)}" if has_phone else "",
                             f"+{rng.randrange(1, 999)} 5{rng.randrange(1000000, 9999999)}" if rng.random() < 0.6 else "",
                             rng.choice(TITLES), rng.choice(DEPARTMENTS), lid("ACC", a), acc[a]["country"], acc[a]["city"],
                             day(-rng.randrange(8000, 22000)), rng.choice(LEAD_SOURCE), f"SBX{rng.randrange(10 ** 9, 10 ** 10)}",
                             pick(rng, {"Email": 50, "Phone": 30, "SMS": 15, "None": 5}), f"@OWNER:{acc[a]['owner']}"])
    save("contact", ["Legacy_Id__c", "FirstName", "LastName", "Email", "Phone", "MobilePhone", "Title", "Department",
                     "Account.Legacy_Id__c", "MailingCountry", "MailingCity", "Birthdate", "LeadSource", "National_Id__c",
                     "Preferred_Channel__c", "OwnerId"], con_rows)
    del con_rows
    for i in range(1, len(acc)):
        hier_rows.append([lid("ACC", i), lid("ACC", acc[i]["parent"]) if acc[i]["parent"] else "", lid("CON", acc_contacts[i][0])])
    save("account_hierarchy", ["Legacy_Id__c", "Parent.Legacy_Id__c", "Primary_Contact__r.Legacy_Id__c"], hier_rows)

    lead_rows = []
    for i in range(1, COUNTS["lead"] + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        country, _, cities = REGIONS[rng.choices(range(len(REGIONS)), weights=region_w)[0]][:3]
        lead_rows.append([lid("LEA", i), first, last, f"{rng.choice(CO_A)} {rng.choice(CO_B)} {rng.choice(CO_C)}", rng.choice(TITLES),
                          f"{first}.{last.replace(' ', '')}.{i}@example.org".lower(), f"+{rng.randrange(1, 999)} {rng.randrange(2000000, 9999999)}",
                          pick(rng, {"Open": 55, "Contacted": 30, "Unqualified": 15}), rng.choice(LEAD_SOURCE), rng.choice(INDUSTRY),
                          country, rng.choice(cities), rng.randrange(5, 5000), f"@OWNER:{rng.randrange(2)}"])
    save("lead", ["Legacy_Id__c", "FirstName", "LastName", "Company", "Title", "Email", "Phone", "Status", "LeadSource", "Industry",
                  "Country", "City", "NumberOfEmployees", "OwnerId"], lead_rows)
    del lead_rows

    # Opportunities and lines (sorted by account, then opportunity, to keep parent locks local)
    opp_acc = [0] + sorted(rng.choice(sales_accounts) for _ in range(COUNTS["opportunity"]))
    opp_won = []
    opp_rows = []
    for o in range(1, len(opp_acc)):
        a = opp_acc[o]
        renewal = rng.random() < 0.3
        r = rng.random()
        if r < 0.3:
            stage, close = "Closed Won", -rng.randrange(1, 720)
            opp_won.append(o)
        elif r < 0.5:
            stage, close = "Closed Lost", -rng.randrange(1, 720)
        else:
            stage, close = rng.choice(OPP_OPEN), rng.randrange(1, 365)
        opp_rows.append([lid("OPP", o), f"{acc[a]['root']} - {rng.choice(PRODUCT_NOUN)} {'Renewal' if renewal else 'Deal'} {o}",
                         lid("ACC", a), f"@RT:Opportunity.{'Renewal' if renewal else 'New_Business'}",
                         "Existing Business" if renewal else "New Business", stage, day(close), rng.randrange(500, 250000, 50),
                         rng.choice(LEAD_SOURCE), "PB-STD", f"@OWNER:{acc[a]['owner']}"])
    save("opportunity", ["Legacy_Id__c", "Name", "Account.Legacy_Id__c", "RecordTypeId", "Type", "StageName", "CloseDate", "Amount",
                         "LeadSource", "Pricebook2.Legacy_Id__c", "OwnerId"], opp_rows)
    del opp_rows
    oli_rows = []
    for o in sorted(rng.randrange(1, len(opp_acc)) for _ in range(COUNTS["opportunity_line"])):
        p = rng.randint(1, COUNTS["product"])
        oli_rows.append([lid("OPP", o), f"@PBE:{lid('PRD', p)}", rng.randint(1, 20), round(price[p] * rng.uniform(0.85, 1.0), 2)])
    save("opportunity_line", ["Opportunity.Legacy_Id__c", "PricebookEntryId", "Quantity", "UnitPrice"], oli_rows)
    del oli_rows
    ocr, ocr_rows = set(), []
    while len(ocr) < COUNTS["contact_role"]:
        o = rng.randrange(1, len(opp_acc))
        ocr.add((o, rng.choice(acc_contacts[opp_acc[o]])))
    seen = set()
    for o, c in sorted(ocr):
        ocr_rows.append([lid("OPP", o), lid("CON", c), rng.choice(OCR_ROLE), "false" if o in seen else "true"])
        seen.add(o)
    save("contact_role", ["Opportunity.Legacy_Id__c", "Contact.Legacy_Id__c", "Role", "IsPrimary"], ocr_rows)
    del ocr, ocr_rows, seen

    for kind, prefix, pool in (("lead", "LEA", COUNTS["lead"]), ("contact", "CON", COUNTS["contact"])):
        members = set()
        while len(members) < COUNTS["campaign_member"] // 2:
            members.add((rng.randint(1, COUNTS["campaign"]), rng.randint(1, pool)))
        save(f"campaign_member_{kind}", ["Campaign.Legacy_Id__c", f"{kind.title()}.Legacy_Id__c", "Status"],
             [[lid("CMP", cm, 3), lid(prefix, m), pick(rng, {"Sent": 70, "Responded": 30})] for cm, m in sorted(members)])

    # Contracts, orders, assets
    save("contract", ["Legacy_Id__c", "Account.Legacy_Id__c", "Status", "StartDate", "ContractTerm", "Description", "OwnerId"],
         # Draft only: the org rejects other statuses on insert. rng.random() keeps the seeded sequence unchanged.
         [[lid("CTR", i), lid("ACC", a), "Draft" if rng.random() >= 0 else "", day(-rng.randrange(-60, 900)),
           rng.choice([12, 24, 36]), "Service agreement", f"@OWNER:{acc[a]['owner']}"]
          for i, a in enumerate(sorted(rng.choice(sales_accounts) for _ in range(COUNTS["contract"])), 1)])
    order_acc = [0] + sorted(rng.choice(sales_accounts) for _ in range(COUNTS["order"]))
    save("order", ["Legacy_Id__c", "Account.Legacy_Id__c", "Status", "EffectiveDate", "Pricebook2.Legacy_Id__c", "Description", "OwnerId"],
         [[lid("ORD", i), lid("ACC", a), "Draft", day(-rng.randrange(0, 700)), "PB-STD", f"Order {i} for {acc[a]['root']}",
           f"@OWNER:{acc[a]['owner']}"] for i, a in enumerate(order_acc[1:], 1)])
    oi_rows = []
    for o in sorted(rng.randrange(1, len(order_acc)) for _ in range(COUNTS["order_item"])):
        p = rng.randint(1, COUNTS["product"])
        oi_rows.append([lid("ORD", o), f"@PBE:{lid('PRD', p)}", rng.randint(1, 10), price[p]])
    save("order_item", ["Order.Legacy_Id__c", "PricebookEntryId", "Quantity", "UnitPrice"], oi_rows)
    del oi_rows
    asset_acc = [0] + sorted(rng.choice(sales_accounts) for _ in range(COUNTS["asset"]))
    asset_rows = []
    for i, a in enumerate(asset_acc[1:], 1):
        p = rng.randint(1, COUNTS["product"])
        installed = -rng.randrange(10, 1500)
        asset_rows.append([lid("AST", i), prod_rows[p - 1][1], lid("ACC", a), lid("CON", rng.choice(acc_contacts[a])), lid("PRD", p),
                           pick(rng, {"Installed": 60, "Registered": 15, "Shipped": 10, "Purchased": 10, "Obsolete": 5}),
                           f"SN-{i:07d}", day(installed), day(installed - rng.randrange(5, 60)), price[p], 1])
    save("asset", ["Legacy_Id__c", "Name", "Account.Legacy_Id__c", "Contact.Legacy_Id__c", "Product2.Legacy_Id__c", "Status",
                   "SerialNumber", "InstallDate", "PurchaseDate", "Price", "Quantity"], asset_rows)
    del asset_rows

    # Cases and service records
    case_acc = [0] + sorted(rng.choice(sales_accounts) for _ in range(COUNTS["case"]))
    case_rows, case_con, closed_cases = [], [0], []
    for i, a in enumerate(case_acc[1:], 1):
        rt = pick(rng, {"Support": 70, "Complaint": 20, "Inspection": 10})
        status = pick(rng, {"New": 15, "On Hold": 10, "Escalated": 5, "Closed": 70})
        if status == "Closed":
            closed_cases.append(i)
        con = rng.choice(acc_contacts[a])
        case_con.append(con)
        if rt == "Complaint":
            owner = "@QUEUE:SBX_Complaints" if status != "Closed" and rng.random() < 0.5 else f"@OWNER:{acc[a]['owner']}"
        else:
            owner = rng.choice(["@QUEUE:SBX_Support_Tier_1", "@QUEUE:SBX_Support_Tier_2"]) if status != "Closed" and rng.random() < 0.4 \
                else f"@OWNER:{acc[a]['owner']}"
        subject = rng.choice(CASE_SUBJECT[rt])
        case_rows.append([lid("CAS", i), f"@RT:Case.{rt}", lid("ACC", a), lid("CON", con), status, rng.choice(["Email", "Phone", "Web"]),
                          rng.choice(CASE_REASON), pick(rng, {"High": 20, "Medium": 50, "Low": 30}),
                          pick(rng, {"Problem": 60, "Question": 30, "Feature Request": 10}), subject,
                          f"{subject}. Reported by the customer at {acc[a]['city']}.", owner])
    save("case", ["Legacy_Id__c", "RecordTypeId", "Account.Legacy_Id__c", "Contact.Legacy_Id__c", "Status", "Origin", "Reason",
                  "Priority", "Type", "Subject", "Description", "OwnerId"], case_rows)
    del case_rows
    by_acc = {}
    for i, a in enumerate(case_acc[1:], 1):
        by_acc.setdefault(a, []).append(i)
    multi = [cases for cases in by_acc.values() if len(cases) > 1]
    parents = set()
    while len(parents) < COUNTS["case_parent"]:
        cases = rng.choice(multi)
        child = rng.choice(cases[1:])
        parents.add((child, cases[0]))
    save("case_parent", ["Legacy_Id__c", "Parent.Legacy_Id__c"], [[lid("CAS", ch), lid("CAS", p)] for ch, p in sorted(parents)])
    save("case_comment", ["Parent.Legacy_Id__c", "CommentBody", "IsPublished"],
         [[lid("CAS", c), rng.choice(["Customer called for an update.", "Technician assigned.", "Waiting for spare part.",
                                      "Remote diagnostics completed.", "Issue reproduced in the lab.", "Customer confirmed the fix."]),
           rng.choice(["true", "false"])] for c in sorted(rng.randrange(1, len(case_acc)) for _ in range(COUNTS["case_comment"]))])
    save("customer_feedback", ["Legacy_Id__c", "Case__r.Legacy_Id__c", "Rating__c", "Comments__c"],
         [[lid("FB", i), lid("CAS", c), r, rng.choice(["Quick resolution.", "Technician was helpful.", "Took too long.",
                                                        "Good communication.", "Problem came back after a week."])]
          for i, (c, r) in enumerate(sorted((rng.choice(closed_cases), rng.randint(1, 5)) for _ in range(COUNTS["customer_feedback"])), 1)])
    sp_rows = []
    for i, a in enumerate(sorted(rng.sample(sales_accounts, COUNTS["support_plan"])), 1):
        tier = pick(rng, {"Bronze": 40, "Silver": 30, "Gold": 20, "Platinum": 10})
        start = -rng.randrange(0, 700)
        sp_rows.append([lid("SP", i), f"{acc[a]['name']} {tier} Plan"[:80], lid("ACC", a), tier, day(start), day(start + 365),
                        {"Bronze": 1200, "Silver": 4800, "Gold": 12000, "Platinum": 30000}[tier]])
    save("support_plan", ["Legacy_Id__c", "Name", "Account__r.Legacy_Id__c", "Tier__c", "Start_Date__c", "End_Date__c", "Annual_Fee__c"], sp_rows)
    del sp_rows
    dr_rows = []
    for i, a in enumerate(sorted(rng.choice(sales_accounts) for _ in range(COUNTS["document_request"])), 1):
        dr_rows.append([lid("DR", i), lid("ACC", a), lid("CON", rng.choice(acc_contacts[a])),
                        rng.choice(["Contract", "Invoice Copy", "Certificate", "Statement"]), pick(rng, {"Requested": 30, "Sent": 40, "Closed": 30})])
    save("document_request", ["Legacy_Id__c", "Account__r.Legacy_Id__c", "Contact__r.Legacy_Id__c", "Document_Type__c", "Status__c"], dr_rows)
    del dr_rows
    skills = set()
    while len(skills) < COUNTS["contact_skill"]:
        skills.add((rng.randint(1, COUNTS["contact"]), rng.randint(1, COUNTS["skill"])))
    save("contact_skill", ["Legacy_Id__c", "Contact__r.Legacy_Id__c", "Skill__r.Legacy_Id__c", "Level__c"],
         [[lid("CSK", i), lid("CON", c), lid("SKL", s, 3), pick(rng, {"Beginner": 30, "Intermediate": 50, "Expert": 20})]
          for i, (c, s) in enumerate(sorted(skills), 1)])
    del skills

    # Suppliers
    sup_rows = []
    for i in range(1, COUNTS["supplier"] + 1):
        cat = rng.choice(list(SUPPLIER_SUB))
        sup_rows.append([lid("SUP", i, 3), f"{rng.choice(CO_A)} {cat} {rng.choice(CO_C)} {i}",
                         lid("REG", rng.choices(range(len(REGIONS)), weights=region_w)[0] + 1, 3), cat, rng.choice(SUPPLIER_SUB[cat]),
                         round(rng.uniform(2.0, 5.0), 1)])
    save("supplier", ["Legacy_Id__c", "Name", "Region__r.Legacy_Id__c", "Category__c", "Sub_Category__c", "Rating__c"], sup_rows)
    supplier_contacts = [c for a in supplier_accounts for c in acc_contacts[a]]
    save("supplier_contact", ["Legacy_Id__c", "Supplier__r.Legacy_Id__c", "Contact__r.Legacy_Id__c", "Role__c"],
         [[lid("SC", i, 4), lid("SUP", s, 3), lid("CON", rng.choice(supplier_contacts)), ["Primary", "Billing", "Technical"][(i - 1) % 3]]
          for i, s in enumerate((n // 3 + 1 for n in range(COUNTS["supplier_contact"])), 1)])

    # Projects
    won_by_acc = {}
    for o in opp_won:
        won_by_acc.setdefault(opp_acc[o], []).append(o)
    proj_acc = [0] + sorted(rng.choice(sales_accounts) for _ in range(COUNTS["project"]))
    proj_rows, acc_projects = [], {}
    for i, a in enumerate(proj_acc[1:], 1):
        acc_projects.setdefault(a, []).append(i)
        internal = rng.random() < 0.2
        start = -rng.randrange(-60, 800)
        status = "Planned" if start > 0 else pick(rng, {"Active": 45, "Completed": 35, "On Hold": 10, "Cancelled": 10})
        opp = rng.choice(won_by_acc[a]) if a in won_by_acc and not internal and rng.random() < 0.6 else None
        proj_rows.append([lid("PRJ", i), f"{acc[a]['root'][:50]} {rng.choice(WP_TASKS)} {i}", lid("ACC", a),
                          f"@RT:Project__c.{'Internal' if internal else 'Client'}", lid("OPP", opp) if opp else "", status, day(start),
                          day(start + rng.randrange(60, 540)), rng.randrange(5000, 900000, 500)])
    save("project", ["Legacy_Id__c", "Name", "Account__r.Legacy_Id__c", "RecordTypeId", "Opportunity__r.Legacy_Id__c", "Status__c",
                     "Start_Date__c", "End_Date__c", "Budget__c"], proj_rows)
    del proj_rows
    multi = [p for p in acc_projects.values() if len(p) > 1]
    pp = {}
    while len(pp) < COUNTS["project_parent"]:
        group = rng.choice(multi)
        pp[rng.choice(group[1:])] = group[0]
    save("project_parent", ["Legacy_Id__c", "Parent_Project__r.Legacy_Id__c"], [[lid("PRJ", ch), lid("PRJ", p)] for ch, p in sorted(pp.items())])
    phase_rows = []
    for p in range(1, COUNTS["project"] + 1):
        for s in range(1, 4):
            ph = (p - 1) * 3 + s
            phase_rows.append([lid("PHS", ph), f"Phase {s} - {PHASES[(s - 1) * 2 + rng.randrange(2)]}", lid("PRJ", p), s,
                               rng.choice(["Not Started", "In Progress", "Done"]), rng.randrange(40, 800)])
    save("project_phase", ["Legacy_Id__c", "Name", "Project__r.Legacy_Id__c", "Sequence__c", "Status__c", "Planned_Hours__c"], phase_rows)
    n_phase = len(phase_rows)
    del phase_rows
    wp_phase = sorted(list(range(1, n_phase + 1)) + [rng.randint(1, n_phase) for _ in range(COUNTS["work_package"] - n_phase)])
    open_wps, wp_rows = [], []
    for i, ph in enumerate(wp_phase, 1):
        status = "Closed" if rng.random() < 0.15 else "Open"
        if status == "Open":
            open_wps.append(i)
        wp_rows.append([lid("WP", i), f"WP {i} - {rng.choice(WP_TASKS)}", lid("PHS", ph), status, rng.randrange(4, 160)])
    save("work_package", ["Legacy_Id__c", "Name", "Project_Phase__r.Legacy_Id__c", "Status__c", "Estimated_Hours__c"], wp_rows)
    del wp_rows
    save("time_entry", ["Legacy_Id__c", "Work_Package__r.Legacy_Id__c", "Contact__r.Legacy_Id__c", "Hours__c", "Entry_Date__c", "Billable__c"],
         [[lid("TE", i, 6), lid("WP", w), lid("CON", rng.randint(1, COUNTS["contact"])), rng.randrange(2, 33) / 4, day(-rng.randrange(0, 600)),
           "true" if rng.random() < 0.75 else "false"]
          for i, w in enumerate(sorted(rng.choice(open_wps) if rng.random() < 0.9 else rng.randint(1, len(wp_phase))
                                       for _ in range(COUNTS["time_entry"])), 1)])
    save("project_supplier", ["Legacy_Id__c", "Project__r.Legacy_Id__c", "Supplier__r.Legacy_Id__c", "Contract_Value__c"],
         [[lid("PS", i), lid("PRJ", p), lid("SUP", rng.randint(1, COUNTS["supplier"]), 3), rng.randrange(1000, 200000, 100)]
          for i, p in enumerate(sorted(rng.randint(1, COUNTS["project"]) for _ in range(COUNTS["project_supplier"])), 1)])

    # Finance
    inv_acc = [0] + sorted(rng.choice(sales_accounts) for _ in range(COUNTS["invoice"]))
    inv_rows, inv_status = [], [None]
    for i, a in enumerate(inv_acc[1:], 1):
        issued = -rng.randrange(0, 540)
        if issued > -7:
            status = "Draft"
        elif rng.random() < 0.03:
            status = "Void"
        elif rng.random() < 0.6:
            status = "Paid"
        else:
            status = "Overdue" if issued + 30 < 0 and rng.random() < 0.7 else "Sent"
        inv_status.append(status)
        proj = rng.choice(acc_projects[a]) if a in acc_projects and rng.random() < 0.6 else None
        inv_rows.append([lid("INV", i), lid("ACC", a), lid("PRJ", proj) if proj else "", day(issued), day(issued + 30), status])
    save("invoice", ["Legacy_Id__c", "Account__r.Legacy_Id__c", "Project__r.Legacy_Id__c", "Invoice_Date__c", "Due_Date__c", "Status__c"], inv_rows)
    del inv_rows
    inv_total = [0.0] * len(inv_acc)
    line_rows = []
    lines = sorted(list(range(1, len(inv_acc))) + [rng.randrange(1, len(inv_acc)) for _ in range(COUNTS["invoice_line"] - len(inv_acc) + 1)])
    for i, inv in enumerate(lines, 1):
        p = rng.randint(1, COUNTS["product"])
        qty = rng.randint(1, 20)
        amount = round(qty * price[p], 2)
        inv_total[inv] += amount
        line_rows.append([lid("INL", i, 6), lid("INV", inv), lid("PRD", p), lid("TAX", rng.randint(1, COUNTS["tax_rate"]), 3), qty, price[p], amount])
    save("invoice_line", ["Legacy_Id__c", "Invoice__r.Legacy_Id__c", "Product__r.Legacy_Id__c", "Tax_Rate__r.Legacy_Id__c", "Quantity__c",
                          "Unit_Price__c", "Amount__c"], line_rows)
    del line_rows
    payable = [i for i in range(1, len(inv_acc)) if inv_status[i] in ("Paid", "Sent", "Overdue")]
    pay_rows = []
    for i, inv in enumerate(sorted(rng.choice(payable) for _ in range(COUNTS["payment"])), 1):
        share = 1.0 if inv_status[inv] == "Paid" else rng.choice([0.25, 0.5])
        pay_rows.append([lid("PAY", i), lid("INV", inv), round(inv_total[inv] * share, 2), day(-rng.randrange(0, 500)),
                         pick(rng, {"Bank Transfer": 60, "Card": 30, "Cheque": 10})])
    save("payment", ["Legacy_Id__c", "Invoice__r.Legacy_Id__c", "Amount__c", "Payment_Date__c", "Method__c"], pay_rows)
    del pay_rows

    # Field operations
    ins_rows = []
    for i, ast in enumerate(sorted(rng.randrange(1, len(asset_acc)) for _ in range(COUNTS["inspection"])), 1):
        ins_rows.append([lid("INS", i), lid("AST", ast), lid("ACC", asset_acc[ast]), day(-rng.randrange(0, 700)),
                         pick(rng, {"Pass": 70, "Conditional": 20, "Fail": 10})])
    save("inspection", ["Legacy_Id__c", "Asset__r.Legacy_Id__c", "Account__r.Legacy_Id__c", "Inspection_Date__c", "Result__c"], ins_rows)
    del ins_rows
    save("inspection_item", ["Legacy_Id__c", "Inspection__r.Legacy_Id__c", "Checklist_Item__c", "Passed__c"],
         [[lid("II", (ins - 1) * 3 + k + 1, 6), lid("INS", ins), item, "true" if rng.random() < 0.88 else "false"]
          for ins in range(1, COUNTS["inspection"] + 1) for k, item in enumerate(rng.sample(CHECKLIST, 3))])

    # Audit and integration
    save("approval_log", ["Legacy_Id__c", "Opportunity__r.Legacy_Id__c", "Decision__c", "Decision_Date__c", "Comments__c"],
         [[lid("APL", i), lid("OPP", o), pick(rng, {"Approved": 75, "Rejected": 25}), stamp(rng, -rng.randrange(1, 700)),
           rng.choice(["Discount within policy.", "Margin below threshold.", "Approved by regional director.", "Needs revised terms."])]
          for i, o in enumerate(sorted(rng.randrange(1, len(opp_acc)) for _ in range(COUNTS["approval_log"])), 1)])
    log_rows = []
    for i in range(1, COUNTS["integration_log"] + 1):
        direction, endpoint = rng.choice(ENDPOINTS)
        code = pick(rng, {200: 70, 201: 10, 400: 6, 401: 3, 404: 4, 500: 5, 503: 2})
        body = {"requestId": f"REQ-{i:07d}", "record": lid("CAS", rng.randint(1, COUNTS["case"])), "status": code,
                "items": [{"line": n, "sku": f"P{rng.randint(1, COUNTS['product']):05d}", "qty": rng.randint(1, 9)} for n in range(rng.randint(1, 12))]}
        if code >= 400:
            body["error"] = {"code": code, "message": "Upstream system rejected the request", "retryable": code >= 500}
        log_rows.append([lid("LOG", i, 6), direction, endpoint, code, json.dumps(body, separators=(",", ":")), stamp(rng, -rng.randrange(0, 365))])
    save("integration_log", ["Legacy_Id__c", "Direction__c", "Endpoint__c", "Status_Code__c", "Payload__c", "Logged_At__c"], log_rows)
    del log_rows

    # Activities: WhatId/WhoId resolved to Ids at load time; lead activities have no WhatId
    def who_what():
        r = rng.random()
        if r < 0.3:
            a = rng.choice(sales_accounts)
            return f"@REC:{lid('ACC', a)}", f"@REC:{lid('CON', rng.choice(acc_contacts[a]))}"
        if r < 0.55:
            o = rng.randrange(1, len(opp_acc))
            return f"@REC:{lid('OPP', o)}", f"@REC:{lid('CON', rng.choice(acc_contacts[opp_acc[o]]))}"
        if r < 0.8:
            c = rng.randrange(1, len(case_acc))
            return f"@REC:{lid('CAS', c)}", f"@REC:{lid('CON', case_con[c])}"
        return "", f"@REC:{lid('LEA', rng.randint(1, COUNTS['lead']))}"

    task_rows = []
    for _ in range(COUNTS["task"]):
        what, who = who_what()
        due = rng.randrange(-540, 60)
        status = ("Completed" if rng.random() < 0.85 else rng.choice(["Deferred", "Waiting on someone else"])) if due < 0 \
            else rng.choice(["Not Started", "In Progress", "Waiting on someone else"])
        task_rows.append([what, who, rng.choice(["Call", "Email", "Send Quote", "Follow up", "Send Letter", "Prepare proposal"]), status,
                          pick(rng, {"High": 20, "Normal": 65, "Low": 15}), day(due), "Logged by the account team.", f"@OWNER:{rng.randrange(2)}"])
    task_rows.sort(key=lambda r: (r[0], r[1]))
    save("task", ["WhatId", "WhoId", "Subject", "Status", "Priority", "ActivityDate", "Description", "OwnerId"], task_rows)
    del task_rows
    event_rows = []
    for _ in range(COUNTS["event"]):
        what, who = who_what()
        start = dt.datetime.fromisoformat(stamp(rng, rng.randrange(-540, 60)).replace(".000Z", ""))
        end = start + dt.timedelta(minutes=rng.choice([30, 45, 60, 90, 120]))
        event_rows.append([what, who, rng.choice(["Meeting", "Site visit", "Demo", "Quarterly review", "Workshop", "Lunch"]),
                           start.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                           rng.choice(["Customer office", "Teams call", "Head office", "Site"]), pick(rng, {"Busy": 80, "OutOfOffice": 5, "Free": 15}),
                           f"@OWNER:{rng.randrange(2)}"])
    event_rows.sort(key=lambda r: (r[0], r[1]))
    save("event", ["WhatId", "WhoId", "Subject", "StartDateTime", "EndDateTime", "Location", "ShowAs", "OwnerId"], event_rows)
    print("Done.", flush=True)


# ---------------------------------------------------------------- load plan

def S(name, obj, op="upsert", main=True):
    return dict(name=name, obj=obj, op=op, ext="Legacy_Id__c" if op == "upsert" else None, main=main)


WAVES = [
    [S("region", "Region__c"), S("tax_rate", "Tax_Rate__c"), S("currency_rate", "Currency_Rate__c"), S("skill", "Skill__c"),
     S("product", "Product2"), S("pricebook", "Pricebook2"), S("campaign", "Campaign")],
    [S("pbe_std", "PricebookEntry", "insert"), S("account", "Account"), S("supplier", "Supplier__c")],
    [S("pbe_custom", "PricebookEntry", "insert"), S("contact", "Contact"), S("lead", "Lead")],
    [S("account_hierarchy", "Account", main=False)],
    [S("opportunity", "Opportunity"), S("contract", "Contract"), S("asset", "Asset"), S("case", "Case"), S("support_plan", "Support_Plan__c"),
     S("document_request", "Document_Request__c"), S("contact_skill", "Contact_Skill__c"), S("supplier_contact", "Supplier_Contact__c"),
     S("campaign_member_lead", "CampaignMember", "insert")],
    [S("opportunity_line", "OpportunityLineItem", "insert"), S("contact_role", "OpportunityContactRole", "insert"), S("order", "Order"),
     S("approval_log", "Approval_Log__c"), S("customer_feedback", "Customer_Feedback__c"), S("case_comment", "CaseComment", "insert"),
     S("inspection", "Inspection__c"), S("project", "Project__c"), S("campaign_member_contact", "CampaignMember", "insert")],
    [S("order_item", "OrderItem", "insert"), S("inspection_item", "Inspection_Item__c"), S("project_phase", "Project_Phase__c"),
     S("project_supplier", "Project_Supplier__c"), S("invoice", "Invoice__c"), S("case_parent", "Case", main=False)],
    [S("work_package", "Work_Package__c"), S("invoice_line", "Invoice_Line__c"), S("payment", "Payment__c")],
    [S("time_entry", "Time_Entry__c"), S("integration_log", "Integration_Log__c"), S("project_parent", "Project__c", main=False)],
    [S("task", "Task", "insert")],
    [S("event", "Event", "insert")],
]


# ---------------------------------------------------------------- Salesforce client

class Org:
    """Talks to the org through the Salesforce CLI, which keeps the session (it never hands out the raw token)."""

    def __init__(self, alias):
        self.alias = alias
        self.sf = shutil.which("sf")
        self.tmp = os.path.join(DATA, "tmp")
        os.makedirs(self.tmp, exist_ok=True)
        info = self.cli(["org", "display"])
        self.version, self.org_id = info["apiVersion"], info["id"]

    def temp(self, suffix):
        return os.path.join(self.tmp, f"{threading.get_ident()}-{time.monotonic_ns()}{suffix}")

    def cli(self, args):
        p = subprocess.run([self.sf, *args, "--target-org", self.alias, "--json"], capture_output=True)
        out = p.stdout.decode("utf-8", "replace")
        res = json.loads(out[out.index("{"):]) if "{" in out else {"message": p.stderr.decode("utf-8", "replace")[:500]}
        if res.get("status") != 0:
            raise RuntimeError(f"sf {' '.join(args[:3])}: {res.get('message')}")
        return res["result"]

    def request(self, method, path, body=None, ctype="application/json", raw=False):
        url = path if path.startswith("/services") else f"/services/data/v{self.version}{path}"
        args = [self.sf, "api", "request", "rest", url, "--method", method, "--include", "--target-org", self.alias,
                "--header", f"Accept:{'text/csv' if raw else 'application/json'}"]
        tmp = None
        if body is not None:
            tmp = self.temp(".body")
            with open(tmp, "wb") as f:
                f.write(body if isinstance(body, bytes) else json.dumps(body).encode())
            args += ["--header", f"Content-Type:{ctype}", "--body", "@" + tmp]
        try:
            for attempt in range(6):
                p = subprocess.run(args, capture_output=True)
                # Output is the status line, then "name: value" headers, then the body (no blank line in between)
                lines = p.stdout.decode("utf-8", "replace").replace("\r\n", "\n").lstrip().split("\n")
                m = re.match(r"HTTP/\S+ (\d+)", lines[0])
                code = int(m.group(1)) if m else 0
                n = 1
                while n < len(lines) and re.match(r"^[A-Za-z0-9-]+: ", lines[n]):
                    n += 1
                payload = "\n".join(lines[n:]).lstrip("\n")
                if 200 <= code < 300:
                    return payload if raw else (json.loads(payload) if payload.strip() else None)
                if (code == 0 or code >= 500) and attempt < 5:
                    time.sleep(10 * (attempt + 1))
                    continue
                detail = payload.strip() or p.stderr.decode("utf-8", "replace")
                raise RuntimeError(f"{method} {url[:90]} -> HTTP {code}: {detail[:500]}")
        finally:
            if tmp:
                os.remove(tmp)

    def query(self, soql):
        """Small REST query; nested relationship values are flattened to 'Rel.Field' keys."""
        def flat(rec, prefix=""):
            out = {}
            for k, v in rec.items():
                if k == "attributes":
                    continue
                if isinstance(v, dict):
                    out.update(flat(v, f"{prefix}{k}."))
                else:
                    out[prefix + k] = v
            return out
        return [flat(r) for r in self.cli(["data", "query", "--query", soql])["records"]]

    def query_bulk(self, soql):
        out = self.temp(".csv")
        self.cli(["data", "export", "bulk", "--query", soql, "--output-file", out, "--result-format", "csv", "--wait", "30"])
        try:
            with open(out, encoding="utf-8", newline="") as f:
                return list(csv.DictReader(f))
        finally:
            os.remove(out)

    def count(self, soql):
        return self.cli(["data", "query", "--query", soql])["totalSize"]

    def ingest(self, obj, op, ext, header, rows):
        """Runs one Bulk API 2.0 ingest job. Returns (succeeded, [(error, row), ...])."""
        spec = {"object": obj, "operation": op, "contentType": "CSV", "lineEnding": "LF"}
        if ext:
            spec["externalIdFieldName"] = ext
        job = self.request("POST", "/jobs/ingest", spec)["id"]
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
        self.request("PUT", f"/jobs/ingest/{job}/batches", buf.getvalue().encode("utf-8"), ctype="text/csv")
        self.request("PATCH", f"/jobs/ingest/{job}", {"state": "UploadComplete"})
        while True:
            time.sleep(8)
            info = self.request("GET", f"/jobs/ingest/{job}")
            if info["state"] in ("JobComplete", "Failed", "Aborted"):
                break
        if info["state"] != "JobComplete":
            raise RuntimeError(f"{obj} job {job} {info['state']}: {info.get('errorMessage')}")
        failed = list(csv.reader(io.StringIO(self.request("GET", f"/jobs/ingest/{job}/failedResults", raw=True))))
        out = []
        if len(failed) > 1:
            cols = failed[0]
            pos = [cols.index(h) for h in header]
            err = cols.index("sf__Error")
            out = [(r[err], [r[p] for p in pos]) for r in failed[1:] if r]
        return info["numberRecordsProcessed"] - info["numberRecordsFailed"], out


class Resolver:
    """Turns @ tokens in the CSVs into Ids from the target org."""
    OBJECTS = {"ACC": "Account", "CON": "Contact", "LEA": "Lead", "OPP": "Opportunity", "CAS": "Case"}

    def __init__(self, org):
        self.org = org
        self.lock = threading.Lock()
        self.maps = {}
        self.rt = {f"{r['SobjectType']}.{r['DeveloperName']}": r["Id"]
                   for r in org.query("SELECT Id, SobjectType, DeveloperName FROM RecordType WHERE IsActive = true")}
        self.queue = {r["DeveloperName"]: r["Id"] for r in org.query("SELECT Id, DeveloperName FROM Group WHERE Type = 'Queue'")}
        self.owner = [r["Id"] for r in org.query(
            "SELECT Id FROM User WHERE IsActive = true AND Profile.Name = 'System Administrator' ORDER BY CreatedDate")]

    def records(self, kind):
        with self.lock:
            if kind not in self.maps:
                if kind == "PBE":
                    recs = self.org.query_bulk("SELECT Id, Product2.Legacy_Id__c FROM PricebookEntry WHERE Pricebook2.IsStandard = true")
                    self.maps[kind] = {r["Product2.Legacy_Id__c"]: r["Id"] for r in recs if r["Product2.Legacy_Id__c"]}
                else:
                    obj = self.OBJECTS[kind]
                    recs = self.org.query_bulk(f"SELECT Id, Legacy_Id__c FROM {obj} WHERE Legacy_Id__c != null")
                    self.maps[kind] = {r["Legacy_Id__c"]: r["Id"] for r in recs}
            return self.maps[kind]

    def value(self, v):
        kind, _, key = v[1:].partition(":")
        if kind == "RT":
            return self.rt.get(key)
        if kind == "QUEUE":
            return self.queue.get(key)
        if kind == "OWNER":
            return self.owner[int(key) % len(self.owner)]
        if kind == "PBE":
            return self.records("PBE").get(key)
        if kind == "REC":
            return self.records(key.split("-")[0]).get(key)
        raise ValueError(f"unknown token {v}")

    def resolve(self, rows):
        good, bad = [], []
        for row in rows:
            out = [self.value(v) if v.startswith("@") else v for v in row]
            missing = [v for v, r in zip(row, out) if r is None]
            if missing:
                bad.append((f"UNRESOLVED_REFERENCE {missing[0]}", row))
            else:
                good.append(out)
        return good, bad


def partitions(header, rows):
    """Splits rows by which external-Id reference columns are filled, so no job sends a blank reference."""
    refs = [i for i, h in enumerate(header) if "." in h]
    groups = {}
    for row in rows:
        groups.setdefault(tuple(i for i in refs if row[i] == ""), []).append(row)
    for blank, part in groups.items():
        keep = [i for i in range(len(header)) if i not in blank]
        yield [header[i] for i in keep], [[r[i] for i in keep] for r in part]


STATE_LOCK = threading.Lock()


def read_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8-sig") as f:
            return json.load(f)
    return {}


def write_state(state):
    with STATE_LOCK:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)


def read_csv(name):
    with open(os.path.join(CSV_DIR, name + ".csv"), encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def run_step(org, resolver, step):
    header, rows = read_csv(step["name"])
    started, total = time.time(), len(rows)
    rows, failures = resolver.resolve(rows)
    failures = [(e, header, r) for e, r in failures]
    ok = 0
    for hdr, part in partitions(header, rows):
        pending = part
        for attempt in range(4):
            done, failed = org.ingest(step["obj"], step["op"], step["ext"], hdr, pending)
            ok += done
            locked = [r for e, r in failed if "UNABLE_TO_LOCK_ROW" in e]
            failures += [(e, hdr, r) for e, r in failed if "UNABLE_TO_LOCK_ROW" not in e]
            if not locked:
                break
            if attempt == 3:
                failures += [("UNABLE_TO_LOCK_ROW after 3 retries", hdr, r) for r in locked]
                break
            print(f"    {step['name']}: retrying {len(locked):,} locked rows", flush=True)
            pending = locked
            time.sleep(15 * (attempt + 1))
    errors = {}
    if failures:
        os.makedirs(FAILED_DIR, exist_ok=True)
        with open(os.path.join(FAILED_DIR, step["name"] + ".csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            for e, hdr, r in failures:
                w.writerow([e] + [f"{h}={v}" for h, v in zip(hdr, r)])
                key = e.split(":")[0][:120]
                errors[key] = errors.get(key, 0) + 1
    return dict(object=step["obj"], rows=total, ok=ok,
                failed=len(failures), errors=errors, seconds=round(time.time() - started))


def set_bypass(org, on):
    recs = org.query(f"SELECT Id FROM Automation_Settings__c WHERE SetupOwnerId = '{org.org_id}'")
    body = {"Bypass_All__c": on, "Bypass_Triggers__c": on, "Bypass_Flows__c": on}
    if recs:
        org.request("PATCH", f"/sobjects/Automation_Settings__c/{recs[0]['Id']}", body)
    else:
        org.request("POST", "/sobjects/Automation_Settings__c", {**body, "SetupOwnerId": org.org_id})
    print(f"Automation bypass {'ON' if on else 'OFF'}", flush=True)


def load(alias, names=()):
    """names: step names to run (default all); a leading '-' excludes a step instead."""
    only = {n for n in names if not n.startswith("-")}
    skip = {n[1:] for n in names if n.startswith("-")}
    org = Org(alias)
    print(f"Target org {alias} ({org.org_id}), API v{org.version}", flush=True)
    state = read_state()
    std = org.query("SELECT Id, Legacy_Id__c FROM Pricebook2 WHERE IsStandard = true")[0]
    if std["Legacy_Id__c"] != "PB-STD":
        org.request("PATCH", f"/sobjects/Pricebook2/{std['Id']}", {"Legacy_Id__c": "PB-STD", "IsActive": True})
    set_bypass(org, True)
    try:
        resolver = Resolver(org)
        for n, wave in enumerate(WAVES, 1):
            todo = [s for s in wave if s["name"] not in state and s["name"] not in skip and (not only or s["name"] in only)]
            if not todo:
                continue
            print(f"Wave {n}: {', '.join(s['name'] for s in todo)}", flush=True)
            broken = []
            with ThreadPoolExecutor(max_workers=len(todo)) as pool:
                futures = {pool.submit(run_step, org, resolver, s): s for s in todo}
                for fut in as_completed(futures):
                    s = futures[fut]
                    try:
                        res = fut.result()
                    except Exception as e:  # leave the step out of the state file so a re-run retries it
                        broken.append(s["name"])
                        print(f"  {s['name']}: ERROR {e}", flush=True)
                        continue
                    state[s["name"]] = res
                    write_state(state)
                    print(f"  {s['name']}: {res['ok']:,}/{res['rows']:,} ok, {res['failed']:,} failed, {res['seconds']}s"
                          + (f" {res['errors']}" if res["errors"] else ""), flush=True)
            if broken:
                print(f"Stopping after wave {n}; failed steps: {', '.join(broken)}", flush=True)
                return 1
    finally:
        set_bypass(org, False)
    print("Load finished.", flush=True)
    return 0


def verify(alias):
    org = Org(alias)
    expected = {}
    for wave in WAVES:
        for s in wave:
            if s["main"]:
                expected[s["obj"]] = expected.get(s["obj"], 0) + len(read_csv(s["name"])[1])
    total_exp = total_org = 0
    print(f"{'Object':28} {'Expected':>10} {'In org':>10}")
    for obj, exp in expected.items():
        where = " WHERE Legacy_Id__c != null" if any(s["obj"] == obj and s["op"] == "upsert" for w in WAVES for s in w) else ""
        n = org.count(f"SELECT COUNT() FROM {obj}{where}")
        total_exp += exp
        total_org += n
        print(f"{obj:28} {exp:>10,} {n:>10,}{'' if n == exp else '  <-- differs'}")
    print(f"{'Total':28} {total_exp:>10,} {total_org:>10,}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "generate":
        generate()
    elif cmd == "load":
        sys.exit(load(sys.argv[2], sys.argv[3:]))
    elif cmd == "verify":
        verify(sys.argv[2])
    else:
        sys.exit(__doc__)
