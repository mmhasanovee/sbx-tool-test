"""Generates the SBX test org metadata (objects, fields, record types, rules,
settings, credentials, roles, queues, groups, permission sets) into force-app.

Run from the project root:  python -I scripts/gen_metadata.py
"""
import os
from xml.sax.saxutils import escape

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "force-app", "main", "default")
NS = 'xmlns="http://soap.sforce.com/2006/04/metadata"'
HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'


def write(rel_path, body):
    path = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER + body)


def label_of(api):
    return api.replace("__c", "").replace("_", " ")


# ---------------------------------------------------------------- field helpers

def text(api, length=80, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Text", "length": length}


def ext_id(api="Legacy_Id__c"):
    return {"api": api, "label": "Legacy Id", "type": "Text", "length": 50, "external": True}


def number(api, precision=10, scale=0, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Number", "precision": precision, "scale": scale}


def currency(api, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Currency", "precision": 16, "scale": 2}


def percent(api, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Percent", "precision": 5, "scale": 2}


def date(api, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Date"}


def datetime(api, label=None):
    return {"api": api, "label": label or label_of(api), "type": "DateTime"}


def checkbox(api, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Checkbox"}


def textarea(api, label=None):
    return {"api": api, "label": label or label_of(api), "type": "TextArea"}


def longtext(api, length=32768, label=None):
    return {"api": api, "label": label or label_of(api), "type": "LongTextArea", "length": length}


def picklist(api, values, label=None, controlling=None, dependencies=None):
    return {"api": api, "label": label or label_of(api), "type": "Picklist", "values": values,
            "controlling": controlling, "dependencies": dependencies or {}}


def lookup(api, ref, rel, required=False, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Lookup", "ref": ref, "rel": rel, "required": required}


def master(api, ref, rel, label=None):
    return {"api": api, "label": label or label_of(api), "type": "MasterDetail", "ref": ref, "rel": rel}


def rollup(api, op, fk, summarized=None, label=None):
    return {"api": api, "label": label or label_of(api), "type": "Summary", "op": op, "fk": fk, "summarized": summarized}


def field_xml(f):
    t = f["type"]
    x = [f"<CustomField {NS}>", f"    <fullName>{f['api']}</fullName>", f"    <label>{escape(f['label'])}</label>"]
    if t == "Text":
        x += [f"    <length>{f['length']}</length>", "    <required>false</required>"]
        if f.get("external"):
            x += ["    <caseSensitive>false</caseSensitive>", "    <externalId>true</externalId>", "    <unique>true</unique>"]
        else:
            x += ["    <externalId>false</externalId>", "    <unique>false</unique>"]
    elif t in ("Number", "Currency", "Percent"):
        x += [f"    <precision>{f['precision']}</precision>", f"    <scale>{f['scale']}</scale>", "    <required>false</required>"]
        if t == "Number":
            x += ["    <externalId>false</externalId>", "    <unique>false</unique>"]
    elif t in ("Date", "DateTime", "TextArea"):
        x += ["    <required>false</required>"]
    elif t == "Checkbox":
        x += ["    <defaultValue>false</defaultValue>"]
    elif t == "LongTextArea":
        x += [f"    <length>{f['length']}</length>", "    <visibleLines>3</visibleLines>"]
    elif t == "Picklist":
        x += ["    <required>false</required>", "    <valueSet>"]
        if f["controlling"]:
            x.append(f"        <controllingField>{f['controlling']}</controllingField>")
        x += ["        <restricted>false</restricted>", "        <valueSetDefinition>", "            <sorted>false</sorted>"]
        for v in f["values"]:
            x += ["            <value>", f"                <fullName>{escape(v)}</fullName>", "                <default>false</default>",
                  f"                <label>{escape(v)}</label>", "            </value>"]
        x.append("        </valueSetDefinition>")
        for value, parents in f["dependencies"].items():
            x.append("        <valueSettings>")
            for p in parents:
                x.append(f"            <controllingFieldValue>{escape(p)}</controllingFieldValue>")
            x += [f"            <valueName>{escape(value)}</valueName>", "        </valueSettings>"]
        x.append("    </valueSet>")
    elif t == "Lookup":
        x += [f"    <deleteConstraint>{'Restrict' if f['required'] else 'SetNull'}</deleteConstraint>",
              f"    <referenceTo>{f['ref']}</referenceTo>",
              f"    <relationshipLabel>{label_of(f['rel'])}</relationshipLabel>",
              f"    <relationshipName>{f['rel']}</relationshipName>",
              f"    <required>{'true' if f['required'] else 'false'}</required>"]
    elif t == "MasterDetail":
        x += [f"    <referenceTo>{f['ref']}</referenceTo>",
              f"    <relationshipLabel>{label_of(f['rel'])}</relationshipLabel>",
              f"    <relationshipName>{f['rel']}</relationshipName>",
              "    <relationshipOrder>0</relationshipOrder>",
              "    <reparentableMasterDetail>false</reparentableMasterDetail>",
              "    <writeRequiresMasterRead>false</writeRequiresMasterRead>"]
    elif t == "Summary":
        if f["summarized"]:
            x.append(f"    <summarizedField>{f['summarized']}</summarizedField>")
        x += [f"    <summaryForeignKey>{f['fk']}</summaryForeignKey>", f"    <summaryOperation>{f['op']}</summaryOperation>"]
    x += [f"    <type>{t}</type>", "</CustomField>\n"]
    return "\n".join(x)


def is_required(f):
    return f["type"] == "MasterDetail" or (f["type"] == "Lookup" and f["required"])


def is_readonly(f):
    return f["type"] == "Summary"


# ---------------------------------------------------------------- custom objects

CUSTOM = {
    "Region__c": dict(label="Region", plural="Regions", name=("Text", "Region Name"), fields=[
        ext_id(), text("Code__c", 10), text("Country__c", 80)]),
    "Tax_Rate__c": dict(label="Tax Rate", plural="Tax Rates", name=("Text", "Tax Rate Name"), fields=[
        ext_id(), percent("Rate__c"), text("Country__c", 80), date("Effective_From__c")]),
    "Currency_Rate__c": dict(label="Currency Rate", plural="Currency Rates", name=("Text", "Rate Name"), fields=[
        ext_id(), text("Currency_Code__c", 3), number("Rate__c", 12, 6), date("Rate_Date__c")]),
    "Skill__c": dict(label="Skill", plural="Skills", name=("Text", "Skill Name"), fields=[
        ext_id(), picklist("Category__c", ["Technical", "Functional", "Soft Skill", "Certification"])]),
    "Support_Plan__c": dict(label="Support Plan", plural="Support Plans", name=("Text", "Plan Name"), fields=[
        ext_id(), lookup("Account__c", "Account", "Support_Plans"),
        picklist("Tier__c", ["Bronze", "Silver", "Gold", "Platinum"]),
        date("Start_Date__c"), date("End_Date__c"), currency("Annual_Fee__c")]),
    "Customer_Feedback__c": dict(label="Customer Feedback", plural="Customer Feedback", name=("AutoNumber", "FB-{000000}", "Feedback No"), fields=[
        ext_id(), lookup("Case__c", "Case", "Customer_Feedback"), number("Rating__c", 1, 0), longtext("Comments__c", 4000)]),
    "Project__c": dict(label="Project", plural="Projects", name=("Text", "Project Name"), detail=True,
                       record_types=["Client", "Internal"], fields=[
        ext_id(), master("Account__c", "Account", "Projects"),
        lookup("Parent_Project__c", "Project__c", "Child_Projects"),
        lookup("Opportunity__c", "Opportunity", "Projects"),
        picklist("Status__c", ["Planned", "Active", "On Hold", "Completed", "Cancelled"]),
        date("Start_Date__c"), date("End_Date__c"), currency("Budget__c"),
        rollup("Total_Phases__c", "count", "Project_Phase__c.Project__c")]),
    "Project_Phase__c": dict(label="Project Phase", plural="Project Phases", name=("Text", "Phase Name"), detail=True, fields=[
        ext_id(), master("Project__c", "Project__c", "Phases"), number("Sequence__c", 3, 0),
        picklist("Status__c", ["Not Started", "In Progress", "Done"]), number("Planned_Hours__c", 8, 1),
        rollup("Total_Work_Packages__c", "count", "Work_Package__c.Project_Phase__c")]),
    "Work_Package__c": dict(label="Work Package", plural="Work Packages", name=("Text", "Work Package Name"), detail=True, fields=[
        ext_id(), master("Project_Phase__c", "Project_Phase__c", "Work_Packages"),
        picklist("Status__c", ["Open", "Closed"]), number("Estimated_Hours__c", 8, 1)]),
    "Time_Entry__c": dict(label="Time Entry", plural="Time Entries", name=("AutoNumber", "TE-{0000000}", "Time Entry No"), fields=[
        ext_id(), lookup("Work_Package__c", "Work_Package__c", "Time_Entries", required=True),
        lookup("Contact__c", "Contact", "Time_Entries"), number("Hours__c", 4, 2), date("Entry_Date__c"), checkbox("Billable__c")]),
    "Invoice__c": dict(label="Invoice", plural="Invoices", name=("AutoNumber", "INV-{000000}", "Invoice No"), fields=[
        ext_id(), lookup("Account__c", "Account", "Invoices"), lookup("Project__c", "Project__c", "Invoices"),
        date("Invoice_Date__c"), date("Due_Date__c"),
        picklist("Status__c", ["Draft", "Sent", "Paid", "Overdue", "Void"]),
        rollup("Total_Amount__c", "sum", "Invoice_Line__c.Invoice__c", "Invoice_Line__c.Amount__c")]),
    "Invoice_Line__c": dict(label="Invoice Line", plural="Invoice Lines", name=("AutoNumber", "INL-{0000000}", "Line No"), detail=True, fields=[
        ext_id(), master("Invoice__c", "Invoice__c", "Invoice_Lines"), lookup("Product__c", "Product2", "Invoice_Lines"),
        lookup("Tax_Rate__c", "Tax_Rate__c", "Invoice_Lines"), number("Quantity__c", 8, 2), currency("Unit_Price__c"), currency("Amount__c")]),
    "Payment__c": dict(label="Payment", plural="Payments", name=("AutoNumber", "PAY-{000000}", "Payment No"), fields=[
        ext_id(), lookup("Invoice__c", "Invoice__c", "Payments"), currency("Amount__c"), date("Payment_Date__c"),
        picklist("Method__c", ["Bank Transfer", "Card", "Cheque"])]),
    "Supplier__c": dict(label="Supplier", plural="Suppliers", name=("Text", "Supplier Name"), fields=[
        ext_id(), lookup("Region__c", "Region__c", "Suppliers"),
        picklist("Category__c", ["Materials", "Services", "Logistics", "Software"]),
        picklist("Sub_Category__c", ["Steel", "Timber", "Consulting", "Maintenance", "Freight", "Warehousing", "Licences", "Cloud"],
                 controlling="Category__c", dependencies={
                     "Steel": ["Materials"], "Timber": ["Materials"], "Consulting": ["Services"], "Maintenance": ["Services"],
                     "Freight": ["Logistics"], "Warehousing": ["Logistics"], "Licences": ["Software"], "Cloud": ["Software"]}),
        number("Rating__c", 2, 1)]),
    "Supplier_Contact__c": dict(label="Supplier Contact", plural="Supplier Contacts", name=("AutoNumber", "SC-{000000}", "Supplier Contact No"), detail=True, fields=[
        ext_id(), master("Supplier__c", "Supplier__c", "Supplier_Contacts"), lookup("Contact__c", "Contact", "Supplier_Contacts"),
        picklist("Role__c", ["Primary", "Billing", "Technical"])]),
    "Project_Supplier__c": dict(label="Project Supplier", plural="Project Suppliers", name=("AutoNumber", "PS-{000000}", "Project Supplier No"), detail=True, fields=[
        ext_id(), master("Project__c", "Project__c", "Project_Suppliers"), lookup("Supplier__c", "Supplier__c", "Project_Suppliers"),
        currency("Contract_Value__c")]),
    "Contact_Skill__c": dict(label="Contact Skill", plural="Contact Skills", name=("AutoNumber", "CS-{000000}", "Contact Skill No"), detail=True, fields=[
        ext_id(), master("Contact__c", "Contact", "Contact_Skills"), lookup("Skill__c", "Skill__c", "Contact_Skills"),
        picklist("Level__c", ["Beginner", "Intermediate", "Expert"])]),
    "Inspection__c": dict(label="Inspection", plural="Inspections", name=("AutoNumber", "INS-{000000}", "Inspection No"), fields=[
        ext_id(), lookup("Asset__c", "Asset", "Inspections"), lookup("Account__c", "Account", "Inspections"),
        date("Inspection_Date__c"), picklist("Result__c", ["Pass", "Fail", "Conditional"])]),
    "Inspection_Item__c": dict(label="Inspection Item", plural="Inspection Items", name=("AutoNumber", "II-{0000000}", "Item No"), detail=True, fields=[
        ext_id(), master("Inspection__c", "Inspection__c", "Inspection_Items"), text("Checklist_Item__c", 255), checkbox("Passed__c")]),
    "Approval_Log__c": dict(label="Approval Log", plural="Approval Logs", name=("AutoNumber", "AL-{000000}", "Approval No"), fields=[
        ext_id(), lookup("Opportunity__c", "Opportunity", "Approval_Logs"), picklist("Decision__c", ["Approved", "Rejected"]),
        datetime("Decision_Date__c"), textarea("Comments__c")]),
    "Document_Request__c": dict(label="Document Request", plural="Document Requests", name=("AutoNumber", "DR-{000000}", "Request No"), fields=[
        ext_id(), lookup("Account__c", "Account", "Document_Requests"), lookup("Contact__c", "Contact", "Document_Requests"),
        picklist("Document_Type__c", ["Contract", "Invoice Copy", "Certificate", "Statement"]),
        picklist("Status__c", ["Requested", "Sent", "Closed"])]),
    "Integration_Log__c": dict(label="Integration Log", plural="Integration Logs", name=("AutoNumber", "LOG-{0000000}", "Log No"), fields=[
        ext_id(), picklist("Direction__c", ["Inbound", "Outbound"]), text("Endpoint__c", 255), number("Status_Code__c", 3, 0),
        longtext("Payload__c", 32768), datetime("Logged_At__c")]),
}

# Custom fields on standard objects
STANDARD = {
    "Account": dict(record_types=["Customer", "Partner", "Supplier"], fields=[
        ext_id(), lookup("Region__c", "Region__c", "Accounts"), lookup("Primary_Contact__c", "Contact", "Primary_For_Accounts"),
        picklist("Customer_Tier__c", ["Strategic", "Key", "Standard"])]),
    "Contact": dict(fields=[ext_id(), text("National_Id__c", 20, "National Id"),
                            picklist("Preferred_Channel__c", ["Email", "Phone", "SMS", "None"])]),
    "Opportunity": dict(record_types=["New_Business", "Renewal"], business_process="Standard_Sales", fields=[ext_id()]),
    "Case": dict(record_types=["Support", "Complaint", "Inspection"], business_process="Standard_Support", fields=[ext_id()]),
    "Lead": dict(fields=[ext_id()]),
    "Campaign": dict(fields=[ext_id()]),
    "Product2": dict(fields=[ext_id()]),
    "Pricebook2": dict(fields=[ext_id()]),
    "Contract": dict(fields=[ext_id()]),
    "Order": dict(fields=[ext_id()]),
    "Asset": dict(fields=[ext_id()]),
}

BUSINESS_PROCESSES = {
    ("Opportunity", "Standard_Sales"): ["Prospecting", "Qualification", "Needs Analysis", "Value Proposition", "Id. Decision Makers",
                                        "Perception Analysis", "Proposal/Price Quote", "Negotiation/Review", "Closed Won", "Closed Lost"],
    ("Case", "Standard_Support"): ["New", "On Hold", "Escalated", "Closed"],
}
DEFAULT_ALLOWED = {"Case"}  # Opportunity sales processes reject a default stage

BYPASS = "$Setup.Automation_Settings__c.Bypass_All__c"
VALIDATION_RULES = {
    ("Contact", "Require_Email_Or_Phone"): (f"AND(NOT({BYPASS}), ISBLANK(Email), ISBLANK(Phone))",
                                            "A contact needs an Email or a Phone."),
    ("Opportunity", "Open_Close_Date_Not_Past"): (f"AND(NOT({BYPASS}), NOT(IsClosed), CloseDate < TODAY())",
                                                  "An open opportunity cannot have a close date in the past."),
    ("Case", "Closed_Requires_Reason"): (f"AND(NOT({BYPASS}), IsClosed, ISBLANK(TEXT(Reason)))",
                                         "Select a Case Reason before closing the case."),
    ("Invoice_Line__c", "Quantity_Positive"): (f"AND(NOT({BYPASS}), Quantity__c <= 0)", "Quantity must be greater than zero."),
    ("Time_Entry__c", "Max_24_Hours"): (f"AND(NOT({BYPASS}), Hours__c > 24)", "A time entry cannot exceed 24 hours."),
}


def build_objects():
    for api, o in CUSTOM.items():
        sharing = "ControlledByParent" if o.get("detail") else "ReadWrite"
        kind = o["name"][0]
        if kind == "AutoNumber":
            name = (f"    <nameField>\n        <displayFormat>{o['name'][1]}</displayFormat>\n"
                    f"        <label>{o['name'][2]}</label>\n        <type>AutoNumber</type>\n    </nameField>")
        else:
            name = f"    <nameField>\n        <label>{o['name'][1]}</label>\n        <type>Text</type>\n    </nameField>"
        write(f"objects/{api}/{api}.object-meta.xml", "\n".join([
            f"<CustomObject {NS}>",
            "    <deploymentStatus>Deployed</deploymentStatus>",
            "    <enableActivities>false</enableActivities>",
            "    <enableBulkApi>true</enableBulkApi>",
            "    <enableHistory>false</enableHistory>",
            "    <enableReports>true</enableReports>",
            "    <enableSearch>true</enableSearch>",
            "    <enableSharing>true</enableSharing>",
            "    <enableStreamingApi>true</enableStreamingApi>",
            f"    <externalSharingModel>{sharing}</externalSharingModel>",
            f"    <label>{o['label']}</label>",
            name,
            f"    <pluralLabel>{o['plural']}</pluralLabel>",
            f"    <sharingModel>{sharing}</sharingModel>",
            "    <visibility>Public</visibility>",
            "</CustomObject>\n"]))
    for api, o in {**CUSTOM, **STANDARD}.items():
        for f in o["fields"]:
            write(f"objects/{api}/fields/{f['api']}.field-meta.xml", field_xml(f))
        for rt in o.get("record_types", []):
            bp = f"\n    <businessProcess>{o['business_process']}</businessProcess>" if o.get("business_process") else ""
            write(f"objects/{api}/recordTypes/{rt}.recordType-meta.xml",
                  f"<RecordType {NS}>\n    <fullName>{rt}</fullName>\n    <active>true</active>{bp}\n"
                  f"    <label>{rt.replace('_', ' ')}</label>\n</RecordType>\n")
    for (obj, name), values in BUSINESS_PROCESSES.items():
        items = "".join(f"    <values>\n        <fullName>{escape(v)}</fullName>\n"
                        f"        <default>{'true' if i == 0 and obj in DEFAULT_ALLOWED else 'false'}</default>\n    </values>\n"
                        for i, v in enumerate(values))
        write(f"objects/{obj}/businessProcesses/{name}.businessProcess-meta.xml",
              f"<BusinessProcess {NS}>\n    <fullName>{name}</fullName>\n    <isActive>true</isActive>\n{items}</BusinessProcess>\n")
    for (obj, name), (formula, message) in VALIDATION_RULES.items():
        write(f"objects/{obj}/validationRules/{name}.validationRule-meta.xml",
              f"<ValidationRule {NS}>\n    <fullName>{name}</fullName>\n    <active>true</active>\n"
              f"    <errorConditionFormula>{escape(formula)}</errorConditionFormula>\n"
              f"    <errorMessage>{escape(message)}</errorMessage>\n</ValidationRule>\n")


# ---------------------------------------------------------------- settings, metadata types, credentials

SETTINGS = {
    "Automation_Settings__c": ("Hierarchy", "Automation Settings",
                               [checkbox("Bypass_All__c"), checkbox("Bypass_Triggers__c"), checkbox("Bypass_Flows__c")]),
    "Integration_Config__c": ("List", "Integration Config", [text("API_Key__c", 255, "API Key"), text("Environment__c", 20)]),
}

ENDPOINTS = {  # Integration_Endpoint__mdt records: system, environment, url, active
    "ERP_Production": ("ERP", "Production", "https://erp.example.com", True),
    "ERP_Sandbox": ("ERP", "Sandbox", "https://erp-sandbox.example.com", False),
    "Payments_Production": ("Payments", "Production", "https://payments.example.com", True),
    "Payments_Sandbox": ("Payments", "Sandbox", "https://payments-sandbox.example.com", False),
}

CREDENTIALS = {  # named credential: (label, url)
    "ERP_API": ("ERP API", "https://erp.example.com"),
    "Payment_Gateway": ("Payment Gateway", "https://payments.example.com"),
}


def build_settings():
    for api, (kind, lbl, fields) in SETTINGS.items():
        write(f"objects/{api}/{api}.object-meta.xml",
              f"<CustomObject {NS}>\n    <customSettingsType>{kind}</customSettingsType>\n    <enableFeeds>false</enableFeeds>\n"
              f"    <label>{lbl}</label>\n    <visibility>Public</visibility>\n</CustomObject>\n")
        for f in fields:
            write(f"objects/{api}/fields/{f['api']}.field-meta.xml", field_xml(f))

    mdt = "Integration_Endpoint__mdt"
    write(f"objects/{mdt}/{mdt}.object-meta.xml",
          f"<CustomObject {NS}>\n    <label>Integration Endpoint</label>\n    <pluralLabel>Integration Endpoints</pluralLabel>\n"
          f"    <visibility>Public</visibility>\n</CustomObject>\n")
    for f in [text("System__c", 40), text("Environment__c", 20), text("Base_URL__c", 255, "Base URL"), checkbox("Active__c")]:
        xml = field_xml(f).replace("</CustomField>", "    <fieldManageability>DeveloperControlled</fieldManageability>\n</CustomField>")
        write(f"objects/{mdt}/fields/{f['api']}.field-meta.xml", xml)
    for dev, (system, env, url, active) in ENDPOINTS.items():
        write(f"customMetadata/Integration_Endpoint.{dev}.md-meta.xml", "\n".join([
            f'<CustomMetadata {NS} xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">',
            f"    <label>{dev.replace('_', ' ')}</label>",
            "    <protected>false</protected>",
            f'    <values>\n        <field>System__c</field>\n        <value xsi:type="xsd:string">{system}</value>\n    </values>',
            f'    <values>\n        <field>Environment__c</field>\n        <value xsi:type="xsd:string">{env}</value>\n    </values>',
            f'    <values>\n        <field>Base_URL__c</field>\n        <value xsi:type="xsd:string">{url}</value>\n    </values>',
            f'    <values>\n        <field>Active__c</field>\n        <value xsi:type="xsd:boolean">{"true" if active else "false"}</value>\n    </values>',
            "</CustomMetadata>\n"]))

    for dev, (lbl, url) in CREDENTIALS.items():
        ext = f"{dev}_Credential"
        write(f"externalCredentials/{ext}.externalCredential-meta.xml", "\n".join([
            f"<ExternalCredential {NS}>",
            "    <authenticationProtocol>Custom</authenticationProtocol>",
            "    <externalCredentialParameters>",
            f"        <parameterGroup>{dev}_Principal</parameterGroup>",
            f"        <parameterName>{dev}_Principal</parameterName>",
            "        <parameterType>NamedPrincipal</parameterType>",
            "        <sequenceNumber>1</sequenceNumber>",
            "    </externalCredentialParameters>",
            f"    <label>{lbl} Credential</label>",
            "</ExternalCredential>\n"]))
        write(f"namedCredentials/{dev}.namedCredential-meta.xml", "\n".join([
            f"<NamedCredential {NS}>",
            "    <allowMergeFieldsInBody>false</allowMergeFieldsInBody>",
            "    <allowMergeFieldsInHeader>false</allowMergeFieldsInHeader>",
            "    <calloutStatus>Enabled</calloutStatus>",
            "    <generateAuthorizationHeader>false</generateAuthorizationHeader>",
            f"    <label>{lbl}</label>",
            "    <namedCredentialParameters>",
            "        <parameterName>Url</parameterName>",
            "        <parameterType>Url</parameterType>",
            f"        <parameterValue>{url}</parameterValue>",
            "    </namedCredentialParameters>",
            "    <namedCredentialParameters>",
            f"        <externalCredential>{ext}</externalCredential>",
            "        <parameterName>ExternalCredential</parameterName>",
            "        <parameterType>Authentication</parameterType>",
            "    </namedCredentialParameters>",
            "    <namedCredentialType>SecuredEndpoint</namedCredentialType>",
            "</NamedCredential>\n"]))
        write(f"remoteSiteSettings/{dev}.remoteSite-meta.xml",
              f"<RemoteSiteSetting {NS}>\n    <disableProtocolSecurity>false</disableProtocolSecurity>\n"
              f"    <isActive>true</isActive>\n    <url>{url}</url>\n</RemoteSiteSetting>\n")


# ---------------------------------------------------------------- roles, queues, groups

ROLES = [("SBX_CEO", "SBX CEO", None),
         ("SBX_VP_Sales", "SBX VP Sales", "SBX_CEO"), ("SBX_Sales_Manager", "SBX Sales Manager", "SBX_VP_Sales"),
         ("SBX_Sales_Rep", "SBX Sales Rep", "SBX_Sales_Manager"),
         ("SBX_VP_Service", "SBX VP Service", "SBX_CEO"), ("SBX_Service_Manager", "SBX Service Manager", "SBX_VP_Service"),
         ("SBX_Support_Agent", "SBX Support Agent", "SBX_Service_Manager"),
         ("SBX_VP_Operations", "SBX VP Operations", "SBX_CEO"), ("SBX_Project_Manager", "SBX Project Manager", "SBX_VP_Operations"),
         ("SBX_Finance_Manager", "SBX Finance Manager", "SBX_CEO")]
QUEUES = [("SBX_Support_Tier_1", "SBX Support Tier 1"), ("SBX_Support_Tier_2", "SBX Support Tier 2"), ("SBX_Complaints", "SBX Complaints")]
GROUPS = [("SBX_Finance_Team", "SBX Finance Team"), ("SBX_Project_Office", "SBX Project Office"), ("SBX_Sales_Team", "SBX Sales Team"),
          ("SBX_Service_Team", "SBX Service Team"), ("SBX_Supplier_Desk", "SBX Supplier Desk")]


def build_org_structure():
    for dev, name, parent in ROLES:
        parent_xml = f"\n    <parentRole>{parent}</parentRole>" if parent else ""
        write(f"roles/{dev}.role-meta.xml",
              f"<Role {NS}>\n    <mayForecastManagerShare>false</mayForecastManagerShare>\n    <name>{name}</name>{parent_xml}\n</Role>\n")
    for dev, name in QUEUES:
        write(f"queues/{dev}.queue-meta.xml",
              f"<Queue {NS}>\n    <doesSendEmailToMembers>false</doesSendEmailToMembers>\n    <name>{name}</name>\n"
              f"    <queueSobject>\n        <sobjectType>Case</sobjectType>\n    </queueSobject>\n</Queue>\n")
    for dev, name in GROUPS:
        write(f"groups/{dev}.group-meta.xml",
              f"<Group {NS}>\n    <doesIncludeBosses>true</doesIncludeBosses>\n    <name>{name}</name>\n</Group>\n")


# ---------------------------------------------------------------- permission sets

ALL = {**CUSTOM, **STANDARD}
PERMISSION_SETS = {  # name: (label, custom objects with full access, standard objects needing read, extra)
    "SBX_Data_Admin": ("SBX Data Admin", list(CUSTOM), list(STANDARD), {"record_types": True, "credentials": True}),
    "SBX_Project_Manager": ("SBX Project Manager", ["Project__c", "Project_Phase__c", "Work_Package__c", "Time_Entry__c",
                                                    "Contact_Skill__c", "Skill__c"], ["Account", "Contact", "Opportunity"], {}),
    "SBX_Finance_User": ("SBX Finance User", ["Invoice__c", "Invoice_Line__c", "Payment__c", "Tax_Rate__c", "Currency_Rate__c"],
                         ["Account", "Product2"], {}),
    "SBX_Support_Agent": ("SBX Support Agent", ["Customer_Feedback__c", "Support_Plan__c"], ["Account", "Case"], {}),
    "SBX_Sales_User": ("SBX Sales User", ["Approval_Log__c", "Document_Request__c"], ["Account", "Contact", "Opportunity"], {}),
    "SBX_Supplier_Manager": ("SBX Supplier Manager", ["Supplier__c", "Supplier_Contact__c", "Region__c"], ["Contact"], {}),
    "SBX_Inspector": ("SBX Inspector", ["Inspection__c", "Inspection_Item__c"], ["Account", "Asset"], {}),
    "SBX_Integration_Access": ("SBX Integration Access", ["Integration_Log__c"], [], {"credentials": True}),
}


def build_permission_sets():
    for name, (lbl, customs, standards, extra) in PERMISSION_SETS.items():
        x = [f"<PermissionSet {NS}>", f"    <description>Sandbox refresh tool test org: {escape(lbl)}</description>"]
        if extra.get("credentials"):
            for dev in CREDENTIALS:
                x += ["    <externalCredentialPrincipalAccesses>", "        <enabled>true</enabled>",
                      f"        <externalCredentialPrincipal>{dev}_Credential-{dev}_Principal</externalCredentialPrincipal>",
                      "    </externalCredentialPrincipalAccesses>"]
        objs = sorted(customs) + (sorted(standards) if name == "SBX_Data_Admin" else [])
        for obj in objs:
            for f in sorted(ALL[obj]["fields"], key=lambda f: f["api"]):
                if is_required(f):
                    continue
                editable = "false" if is_readonly(f) else "true"
                x += ["    <fieldPermissions>", f"        <editable>{editable}</editable>",
                      f"        <field>{obj}.{f['api']}</field>", "        <readable>true</readable>", "    </fieldPermissions>"]
        x += ["    <hasActivationRequired>false</hasActivationRequired>", f"    <label>{escape(lbl)}</label>"]
        for obj in sorted(set(customs) | set(standards)):
            full = obj in customs
            x += ["    <objectPermissions>",
                  f"        <allowCreate>{'true' if full else 'false'}</allowCreate>",
                  f"        <allowDelete>{'true' if full else 'false'}</allowDelete>",
                  f"        <allowEdit>{'true' if full else 'false'}</allowEdit>",
                  "        <allowRead>true</allowRead>",
                  "        <modifyAllRecords>false</modifyAllRecords>",
                  f"        <object>{obj}</object>",
                  "        <viewAllRecords>false</viewAllRecords>",
                  "    </objectPermissions>"]
        if extra.get("record_types"):
            for obj, o in sorted(ALL.items()):
                for rt in o.get("record_types", []):
                    x += ["    <recordTypeVisibilities>", f"        <recordType>{obj}.{rt}</recordType>",
                          "        <visible>true</visible>", "    </recordTypeVisibilities>"]
        x.append("</PermissionSet>\n")
        write(f"permissionsets/{name}.permissionset-meta.xml", "\n".join(x))


# ---------------------------------------------------------------- duplicate management (deployed in a second pass)

def build_duplicate_rules():
    write("matchingRules/Contact.matchingRule-meta.xml", "\n".join([
        f"<MatchingRules {NS}>",
        "    <matchingRules>",
        "        <fullName>SBX_Contact_Email_Match</fullName>",
        "        <label>SBX Contact Email Match</label>",
        "        <matchingRuleItems>",
        "            <blankValueBehavior>NullNotAllowed</blankValueBehavior>",
        "            <fieldName>Email</fieldName>",
        "            <matchingMethod>Exact</matchingMethod>",
        "        </matchingRuleItems>",
        "        <ruleStatus>Active</ruleStatus>",
        "    </matchingRules>",
        "</MatchingRules>\n"]))
    write("duplicateRules/Contact.SBX_Contact_Email_Duplicate.duplicateRule-meta.xml", "\n".join([
        f'<DuplicateRule {NS} xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        "    <actionOnInsert>Block</actionOnInsert>",
        "    <actionOnUpdate>Block</actionOnUpdate>",
        "    <alertText>A contact with this email already exists.</alertText>",
        "    <description>Blocks duplicate contacts by email.</description>",
        "    <duplicateRuleFilter xsi:nil=\"true\"/>",
        "    <duplicateRuleMatchRules>",
        "        <matchRuleSObjectType>Contact</matchRuleSObjectType>",
        "        <matchingRule>SBX_Contact_Email_Match</matchingRule>",
        "        <objectMapping xsi:nil=\"true\"/>",
        "    </duplicateRuleMatchRules>",
        "    <isActive>true</isActive>",
        "    <masterLabel>SBX Contact Email Duplicate</masterLabel>",
        "    <securityOption>EnforceSharingRules</securityOption>",
        "    <sortOrder>2</sortOrder>",  # 1 is the org's standard Contact-vs-Lead rule
        "</DuplicateRule>\n"]))


if __name__ == "__main__":
    build_objects()
    build_settings()
    build_org_structure()
    build_permission_sets()
    build_duplicate_rules()
    print("metadata generated in", os.path.normpath(ROOT))
