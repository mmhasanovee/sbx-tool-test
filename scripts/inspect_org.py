"""Snapshots the parts of an org that sandbox tooling changes, and diffs two snapshots.

Run from the project root:
    python -I scripts/inspect_org.py snapshot SBX-TOOL-PROD baseline   # writes data/snapshots/baseline.json
    python -I scripts/inspect_org.py snapshot SBXDEV01                  # label defaults to the alias
    python -I scripts/inspect_org.py diff baseline SBXDEV01             # prints what changed, writes data/snapshots/diff_<a>_<b>.json

Sandbox usernames carry an extra ".<sandbox>" suffix and org-level Ids change, so rows are keyed by
names that survive a copy. Things the API can't read (Email Deliverability, External Credential secrets)
still need a Setup screenshot.
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load_data import DATA, WAVES, Org  # noqa: E402

SNAPSHOTS = os.path.join(DATA, "snapshots")
OBJECTS = sorted({s["obj"] for wave in WAVES for s in wave} | {"Pricebook2"})
URL = re.compile(r"https?://[A-Za-z0-9.-]+")


def keyed(rows, key):
    return {key(r): {k: v for k, v in r.items()} for r in rows}


def snapshot(alias, label=None):
    org = Org(alias)
    info = org.query("SELECT Id, Name, IsSandbox, OrganizationType, InstanceName FROM Organization")[0]
    snap = {"taken_at": dt.datetime.now().isoformat(timespec="seconds"), "alias": alias, "org": info}

    # SOQL leaves Endpoint blank for named credentials backed by an external credential; the Connect API has the URL
    snap["named_credentials"] = {}
    for r in org.query("SELECT DeveloperName FROM NamedCredential"):
        nc = org.request("GET", f"/named-credentials/named-credential-setup/{r['DeveloperName']}")
        snap["named_credentials"][r["DeveloperName"]] = {"calloutUrl": nc.get("calloutUrl"), "calloutStatus": nc.get("calloutStatus")}
    snap["remote_sites"] = keyed(org.query("SELECT SiteName, EndpointUrl, IsActive FROM RemoteProxy", tooling=True), lambda r: r["SiteName"])
    snap["endpoint_mdt"] = keyed(org.query("SELECT DeveloperName, System__c, Base_URL__c, Active__c FROM Integration_Endpoint__mdt"),
                                 lambda r: r["DeveloperName"])
    snap["integration_config"] = keyed(org.query("SELECT Name, Environment__c, API_Key__c FROM Integration_Config__c"), lambda r: r["Name"])
    snap["automation_settings"] = keyed(
        org.query("SELECT SetupOwnerId, Bypass_All__c, Bypass_Triggers__c, Bypass_Flows__c FROM Automation_Settings__c"),
        lambda r: "org default" if r.pop("SetupOwnerId").startswith("00D") else "user/profile override")

    # Only our own classes, and only the URLs written in them
    classes = org.query("SELECT Name, Body FROM ApexClass WHERE NamespacePrefix = null", tooling=True)
    snap["apex_urls"] = {c["Name"]: sorted(set(URL.findall(c["Body"] or ""))) for c in classes if URL.search(c["Body"] or "")}
    snap["apex_classes"] = sorted(c["Name"] for c in classes)

    snap["triggers"] = keyed(org.query("SELECT Name, Status, TableEnumOrId FROM ApexTrigger WHERE NamespacePrefix = null", tooling=True),
                             lambda r: r["Name"])
    snap["flows"] = keyed(org.query("SELECT ApiName, IsActive, ProcessType FROM FlowDefinitionView WHERE NamespacePrefix = null"),
                          lambda r: r["ApiName"])
    snap["validation_rules"] = keyed(
        org.query("SELECT ValidationName, Active, EntityDefinition.QualifiedApiName FROM ValidationRule WHERE NamespacePrefix = null",
                  tooling=True),
        lambda r: f"{r['EntityDefinition.QualifiedApiName']}.{r['ValidationName']}")
    snap["workflow_rules"] = sorted(r["Name"] for r in org.query("SELECT Name FROM WorkflowRule WHERE NamespacePrefix = null", tooling=True))
    snap["scheduled_jobs"] = keyed(
        org.query("SELECT CronJobDetail.Name, CronExpression, State, NextFireTime FROM CronTrigger WHERE CronJobDetail.JobType = '7'"),
        lambda r: r["CronJobDetail.Name"])
    snap["saml_configs"] = sorted(m["fullName"] for m in org.cli(["org", "list", "metadata", "--metadata-type", "SamlSsoConfig"]) or [])

    principals = {}
    for name in ("ERP_API_Credential", "Payment_Gateway_Credential"):
        try:
            ec = org.request("GET", f"/named-credentials/external-credentials/{name}")
            # Secret values are never returned, only the parameter names that hold one
            principals[name] = {p.get("principalName"): {"status": p.get("authenticationStatus"),
                                                         "parameters": sorted(x.get("parameterName") for x in p.get("parameters", []))}
                                for p in ec.get("principals", [])}
        except RuntimeError as e:
            principals[name] = {"error": str(e)[:200]}
    snap["external_credential_principals"] = principals

    # A sandbox appends ".<sandbox name>" to every username; strip it so users line up with Production
    users = org.query("SELECT Username, Email, IsActive, Profile.Name FROM User WHERE UserType = 'Standard' OR Profile.Name = 'Chatter Free User'")
    strip = (lambda u: re.sub(r"\.[a-z0-9]+$", "", u)) if info["IsSandbox"] else (lambda u: u)
    snap["users"] = keyed(users, lambda r: strip(r.pop("Username")))
    snap["user_summary"] = {
        "total": len(users),
        "active": sum(1 for u in users if u["IsActive"]),
        "email_invalid_suffix": sum(1 for u in users if (u["Email"] or "").endswith(".invalid")),
    }

    snap["post_copy_runs"] = [r["Payload__c"] for r in
                              org.query("SELECT Payload__c FROM Integration_Log__c WHERE Endpoint__c = 'SandboxPostCopy' ORDER BY Logged_At__c")]
    snap["record_counts"] = {obj: org.count(f"SELECT COUNT() FROM {obj}") for obj in OBJECTS}

    os.makedirs(SNAPSHOTS, exist_ok=True)
    path = os.path.join(SNAPSHOTS, f"{label or alias}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, sort_keys=True, default=str)
    s = snap["user_summary"]
    print(f"Saved {path}")
    print(f"  {info['Name']} ({'sandbox' if info['IsSandbox'] else 'production'}), {len(snap['flows'])} flows, "
          f"{len(snap['triggers'])} triggers, {len(snap['validation_rules'])} validation rules, {len(snap['scheduled_jobs'])} scheduled jobs, "
          f"{s['active']}/{s['total']} users active, {sum(snap['record_counts'].values()):,} records")
    return snap


def compare(a, b):
    """Returns {section: [change, ...]} for every section that differs."""
    skip = {"taken_at", "alias", "org"}
    out = {}
    for section in sorted(set(a) | set(b) - skip):
        if section in skip:
            continue
        x, y = a.get(section), b.get(section)
        if x == y:
            continue
        changes = []
        if isinstance(x, dict) and isinstance(y, dict):
            for key in sorted(set(x) | set(y)):
                if key not in y:
                    changes.append(f"- {key}: only in A")
                elif key not in x:
                    changes.append(f"+ {key}: only in B {json.dumps(y[key], default=str)}")
                elif x[key] != y[key]:
                    if isinstance(x[key], dict) and isinstance(y[key], dict):
                        diffs = [f"{f} {x[key].get(f)!r} -> {y[key].get(f)!r}" for f in sorted(set(x[key]) | set(y[key]))
                                 if x[key].get(f) != y[key].get(f)]
                        changes.append(f"~ {key}: {', '.join(diffs)}")
                    else:
                        changes.append(f"~ {key}: {x[key]!r} -> {y[key]!r}")
        elif isinstance(x, list) and isinstance(y, list):
            changes += [f"- {v}" for v in x if v not in y] + [f"+ {v}" for v in y if v not in x]
        else:
            changes.append(f"~ {x!r} -> {y!r}")
        out[section] = changes
    return out


def load_snapshot(label):
    with open(os.path.join(SNAPSHOTS, f"{label}.json"), encoding="utf-8") as f:
        return json.load(f)


def diff(label_a, label_b):
    a, b = load_snapshot(label_a), load_snapshot(label_b)
    result = compare(a, b)
    print(f"A = {label_a} ({a['org']['Name']}, {a['taken_at']})")
    print(f"B = {label_b} ({b['org']['Name']}, {b['taken_at']})")
    if not result:
        print("No differences.")
    for section, changes in result.items():
        print(f"\n[{section}]")
        for c in changes:
            print(f"  {c}")
    path = os.path.join(SNAPSHOTS, f"diff_{label_a}_{label_b}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved {path}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "snapshot" and len(sys.argv) >= 3:
        snapshot(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "diff" and len(sys.argv) == 4:
        diff(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
