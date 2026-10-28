"""Writes the Apex classes, triggers and record-triggered flows for the SBX test org.

Run from the project root:  python -I scripts/gen_apex.py
"""
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "force-app", "main", "default")
API = "67.0"
HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'
NS = 'xmlns="http://soap.sforce.com/2006/04/metadata"'


def write(rel_path, body):
    path = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)


def apex_class(name, body):
    write(f"classes/{name}.cls", body)
    write(f"classes/{name}.cls-meta.xml",
          f"{HEADER}<ApexClass {NS}>\n    <apiVersion>{API}</apiVersion>\n    <status>Active</status>\n</ApexClass>\n")


def apex_trigger(name, body):
    write(f"triggers/{name}.trigger", body)
    write(f"triggers/{name}.trigger-meta.xml",
          f"{HEADER}<ApexTrigger {NS}>\n    <apiVersion>{API}</apiVersion>\n    <status>Active</status>\n</ApexTrigger>\n")


CLASSES = {
    "AutomationSettings": """/**
 * Reads the Automation_Settings__c bypass switches used by triggers, flows and validation rules.
 */
public with sharing class AutomationSettings {
    public static Boolean bypassTriggers() {
        Automation_Settings__c settings = Automation_Settings__c.getInstance();
        return settings != null && (settings.Bypass_All__c == true || settings.Bypass_Triggers__c == true);
    }
}
""",
    "AccountRegionService": """/**
 * Assigns Region__c on accounts from their billing country.
 */
public with sharing class AccountRegionService {
    public static void assignRegions(List<Account> accounts) {
        Set<String> countries = new Set<String>();
        for (Account acc : accounts) {
            if (acc.Region__c == null && String.isNotBlank(acc.BillingCountry)) {
                countries.add(acc.BillingCountry);
            }
        }
        if (countries.isEmpty()) {
            return;
        }
        Map<String, Id> regionByCountry = new Map<String, Id>();
        for (Region__c region : [SELECT Id, Country__c FROM Region__c WHERE Country__c IN :countries WITH SYSTEM_MODE]) {
            regionByCountry.put(region.Country__c, region.Id);
        }
        for (Account acc : accounts) {
            if (acc.Region__c == null && regionByCountry.containsKey(acc.BillingCountry)) {
                acc.Region__c = regionByCountry.get(acc.BillingCountry);
            }
        }
    }
}
""",
    "ErpCaseSyncJob": """/**
 * Sends new case ids to the ERP through the ERP_API named credential and logs the result.
 * In a refreshed sandbox the named credential must point at a sandbox endpoint.
 */
public with sharing class ErpCaseSyncJob implements Queueable, Database.AllowsCallouts {
    private final Set<Id> caseIds;

    public ErpCaseSyncJob(Set<Id> caseIds) {
        this.caseIds = caseIds;
    }

    public void execute(QueueableContext context) {
        HttpRequest request = new HttpRequest();
        request.setEndpoint('callout:ERP_API/cases');
        request.setMethod('POST');
        request.setHeader('Content-Type', 'application/json');
        request.setBody(JSON.serialize(caseIds));

        Integration_Log__c log = new Integration_Log__c(
            Direction__c = 'Outbound',
            Endpoint__c = 'callout:ERP_API/cases',
            Logged_At__c = System.now()
        );
        try {
            HttpResponse response = new Http().send(request);
            String body = response.getBody();
            log.Status_Code__c = response.getStatusCode();
            log.Payload__c = body == null ? null : body.left(32000);
        } catch (Exception e) {
            log.Status_Code__c = 0;
            log.Payload__c = e.getMessage().left(32000);
        }
        insert as system log;
    }
}
""",
    "TimeEntryService": """/**
 * Stops time being logged against closed work packages.
 */
public with sharing class TimeEntryService {
    public static void blockClosedWorkPackages(List<Time_Entry__c> entries) {
        Set<Id> workPackageIds = new Set<Id>();
        for (Time_Entry__c entry : entries) {
            if (entry.Work_Package__c != null) {
                workPackageIds.add(entry.Work_Package__c);
            }
        }
        if (workPackageIds.isEmpty()) {
            return;
        }
        Map<Id, Work_Package__c> closed = new Map<Id, Work_Package__c>(
            [SELECT Id FROM Work_Package__c WHERE Id IN :workPackageIds AND Status__c = 'Closed' WITH SYSTEM_MODE]
        );
        for (Time_Entry__c entry : entries) {
            if (closed.containsKey(entry.Work_Package__c)) {
                entry.addError('Time cannot be logged against a closed work package.');
            }
        }
    }
}
""",
    "InvoiceOverdueBatch": """/**
 * Nightly job: marks sent invoices past their due date as Overdue.
 */
public with sharing class InvoiceOverdueBatch implements Database.Batchable<SObject>, Schedulable {
    public Database.QueryLocator start(Database.BatchableContext context) {
        return Database.getQueryLocator(
            'SELECT Id FROM Invoice__c WHERE Status__c = \\'Sent\\' AND Due_Date__c < TODAY',
            AccessLevel.SYSTEM_MODE
        );
    }

    public void execute(Database.BatchableContext context, List<Invoice__c> scope) {
        for (Invoice__c invoice : scope) {
            invoice.Status__c = 'Overdue';
        }
        update as system scope;
    }

    public void finish(Database.BatchableContext context) {
    }

    public void execute(SchedulableContext context) {
        Database.executeBatch(new InvoiceOverdueBatch(), 200);
    }
}
""",
    "IntegrationSyncScheduler": """/**
 * Hourly job: records a heartbeat against the active ERP endpoint from Integration_Endpoint__mdt.
 */
public with sharing class IntegrationSyncScheduler implements Schedulable {
    public void execute(SchedulableContext context) {
        List<Integration_Endpoint__mdt> endpoints = [
            SELECT Base_URL__c FROM Integration_Endpoint__mdt WHERE System__c = 'ERP' AND Active__c = true WITH SYSTEM_MODE LIMIT 1
        ];
        insert as system new Integration_Log__c(
            Direction__c = 'Outbound',
            Endpoint__c = endpoints.isEmpty() ? null : endpoints[0].Base_URL__c,
            Status_Code__c = 202,
            Payload__c = 'Scheduled sync heartbeat',
            Logged_At__c = System.now()
        );
    }
}
""",
    "SbxAutomationTest": """@IsTest
private class SbxAutomationTest {
    private class ErpMock implements HttpCalloutMock {
        private final Boolean fail;

        ErpMock(Boolean fail) {
            this.fail = fail;
        }

        public HttpResponse respond(HttpRequest request) {
            if (fail) {
                throw new CalloutException('ERP unavailable');
            }
            HttpResponse response = new HttpResponse();
            response.setStatusCode(200);
            response.setBody('{"status":"ok"}');
            return response;
        }
    }

    private static Work_Package__c createWorkPackage(String status) {
        Account acc = new Account(Name = 'SBX Test Account');
        insert as system acc;
        Project__c project = new Project__c(Name = 'SBX Test Project', Account__c = acc.Id);
        insert as system project;
        Project_Phase__c phase = new Project_Phase__c(Name = 'Build', Project__c = project.Id);
        insert as system phase;
        Work_Package__c workPackage = new Work_Package__c(Name = 'WP 1', Project_Phase__c = phase.Id, Status__c = status);
        insert as system workPackage;
        return workPackage;
    }

    @IsTest
    static void assignsRegionFromBillingCountry() {
        Region__c region = new Region__c(Name = 'Gulf', Country__c = 'Kuwait');
        insert as system region;

        Account acc = new Account(Name = 'Region Test', BillingCountry = 'Kuwait');
        insert as system acc;

        Assert.areEqual(region.Id, [SELECT Region__c FROM Account WHERE Id = :acc.Id WITH SYSTEM_MODE].Region__c);
    }

    @IsTest
    static void bypassSkipsTriggers() {
        insert as system new Automation_Settings__c(SetupOwnerId = UserInfo.getOrganizationId(), Bypass_All__c = true);
        insert as system new Region__c(Name = 'Gulf', Country__c = 'Kuwait');

        Account acc = new Account(Name = 'Bypass Test', BillingCountry = 'Kuwait');
        insert as system acc;

        Assert.isNull([SELECT Region__c FROM Account WHERE Id = :acc.Id WITH SYSTEM_MODE].Region__c);
    }

    @IsTest
    static void caseInsertLogsErpCallout() {
        Test.setMock(HttpCalloutMock.class, new ErpMock(false));

        Test.startTest();
        insert as system new Case(Subject = 'Callout test', Status = 'New');
        Test.stopTest();

        Integration_Log__c log = [SELECT Status_Code__c FROM Integration_Log__c WITH SYSTEM_MODE LIMIT 1];
        Assert.areEqual(200, log.Status_Code__c);
    }

    @IsTest
    static void failedCalloutIsLogged() {
        Test.setMock(HttpCalloutMock.class, new ErpMock(true));

        Test.startTest();
        insert as system new Case(Subject = 'Callout failure test', Status = 'New');
        Test.stopTest();

        Integration_Log__c log = [SELECT Status_Code__c, Payload__c FROM Integration_Log__c WITH SYSTEM_MODE LIMIT 1];
        Assert.areEqual(0, log.Status_Code__c);
        Assert.areEqual('ERP unavailable', log.Payload__c);
    }

    @IsTest
    static void blocksTimeOnClosedWorkPackage() {
        Work_Package__c workPackage = createWorkPackage('Closed');

        Database.SaveResult result = Database.insert(
            new Time_Entry__c(Work_Package__c = workPackage.Id, Hours__c = 2), false, AccessLevel.SYSTEM_MODE
        );

        Assert.isFalse(result.isSuccess());
    }

    @IsTest
    static void allowsTimeOnOpenWorkPackage() {
        Work_Package__c workPackage = createWorkPackage('Open');

        insert as system new Time_Entry__c(Work_Package__c = workPackage.Id, Hours__c = 2);

        Assert.areEqual(1, [SELECT COUNT() FROM Time_Entry__c WITH SYSTEM_MODE]);
    }

    @IsTest
    static void marksOverdueInvoices() {
        Account acc = new Account(Name = 'Invoice Test');
        insert as system acc;
        Invoice__c invoice = new Invoice__c(Account__c = acc.Id, Status__c = 'Sent', Due_Date__c = Date.today().addDays(-1));
        insert as system invoice;

        Test.startTest();
        new InvoiceOverdueBatch().execute((SchedulableContext) null);
        Test.stopTest();

        Assert.areEqual('Overdue', [SELECT Status__c FROM Invoice__c WHERE Id = :invoice.Id WITH SYSTEM_MODE].Status__c);
    }

    @IsTest
    static void schedulerLogsHeartbeat() {
        new IntegrationSyncScheduler().execute((SchedulableContext) null);

        Assert.areEqual(1, [SELECT COUNT() FROM Integration_Log__c WITH SYSTEM_MODE]);
    }
}
""",
}

TRIGGERS = {
    "AccountTrigger": """trigger AccountTrigger on Account (before insert, before update) {
    if (AutomationSettings.bypassTriggers()) {
        return;
    }
    AccountRegionService.assignRegions(Trigger.new);
}
""",
    "CaseTrigger": """trigger CaseTrigger on Case (after insert) {
    if (AutomationSettings.bypassTriggers()) {
        return;
    }
    System.enqueueJob(new ErpCaseSyncJob(Trigger.newMap.keySet()));
}
""",
    "TimeEntryTrigger": """trigger TimeEntryTrigger on Time_Entry__c (before insert, before update) {
    if (AutomationSettings.bypassTriggers()) {
        return;
    }
    TimeEntryService.blockClosedWorkPackages(Trigger.new);
}
""",
}

FLOW_META = """    <processMetadataValues>
        <name>BuilderType</name>
        <value>
            <stringValue>LightningFlowBuilder</stringValue>
        </value>
    </processMetadataValues>
    <processMetadataValues>
        <name>CanvasMode</name>
        <value>
            <stringValue>AUTO_LAYOUT_CANVAS</stringValue>
        </value>
    </processMetadataValues>
    <processMetadataValues>
        <name>OriginBuilderType</name>
        <value>
            <stringValue>LightningFlowBuilder</stringValue>
        </value>
    </processMetadataValues>
"""

BYPASS_FLOWS = "OR({!$Setup.Automation_Settings__c.Bypass_All__c}, {!$Setup.Automation_Settings__c.Bypass_Flows__c})"

FLOWS = {
    "SBX_Opportunity_Won_Create_Project": f"""{HEADER}<Flow {NS}>
    <apiVersion>{API}</apiVersion>
    <description>When an opportunity is Closed Won, creates a project for its account.</description>
    <environments>Default</environments>
    <formulas>
        <name>ProjectName</name>
        <dataType>String</dataType>
        <expression>LEFT({{!$Record.Name}}, 80)</expression>
    </formulas>
    <interviewLabel>SBX Opportunity Won Create Project {{!$Flow.CurrentDateTime}}</interviewLabel>
    <label>SBX Opportunity Won - Create Project</label>
{FLOW_META}    <processType>AutoLaunchedFlow</processType>
    <recordCreates>
        <name>Create_Project</name>
        <label>Create Project</label>
        <locationX>176</locationX>
        <locationY>323</locationY>
        <inputAssignments>
            <field>Account__c</field>
            <value>
                <elementReference>$Record.AccountId</elementReference>
            </value>
        </inputAssignments>
        <inputAssignments>
            <field>Name</field>
            <value>
                <elementReference>ProjectName</elementReference>
            </value>
        </inputAssignments>
        <inputAssignments>
            <field>Opportunity__c</field>
            <value>
                <elementReference>$Record.Id</elementReference>
            </value>
        </inputAssignments>
        <inputAssignments>
            <field>Status__c</field>
            <value>
                <stringValue>Planned</stringValue>
            </value>
        </inputAssignments>
        <object>Project__c</object>
        <storeOutputAutomatically>true</storeOutputAutomatically>
    </recordCreates>
    <start>
        <locationX>50</locationX>
        <locationY>0</locationY>
        <connector>
            <targetReference>Create_Project</targetReference>
        </connector>
        <doesRequireRecordChangedToMeetCriteria>true</doesRequireRecordChangedToMeetCriteria>
        <filterFormula>AND(NOT({BYPASS_FLOWS}), ISPICKVAL({{!$Record.StageName}}, &quot;Closed Won&quot;), NOT(ISBLANK({{!$Record.AccountId}})))</filterFormula>
        <object>Opportunity</object>
        <recordTriggerType>CreateAndUpdate</recordTriggerType>
        <triggerType>RecordAfterSave</triggerType>
    </start>
    <status>Active</status>
</Flow>
""",
    "SBX_Case_Set_Priority": f"""{HEADER}<Flow {NS}>
    <apiVersion>{API}</apiVersion>
    <assignments>
        <name>Set_High_Priority</name>
        <label>Set High Priority</label>
        <locationX>176</locationX>
        <locationY>287</locationY>
        <assignmentItems>
            <assignToReference>$Record.Priority</assignToReference>
            <operator>Assign</operator>
            <value>
                <stringValue>High</stringValue>
            </value>
        </assignmentItems>
    </assignments>
    <description>New cases with reason Existing problem get High priority.</description>
    <environments>Default</environments>
    <interviewLabel>SBX Case Set Priority {{!$Flow.CurrentDateTime}}</interviewLabel>
    <label>SBX Case - Set Priority</label>
{FLOW_META}    <processType>AutoLaunchedFlow</processType>
    <start>
        <locationX>50</locationX>
        <locationY>0</locationY>
        <connector>
            <targetReference>Set_High_Priority</targetReference>
        </connector>
        <filterFormula>AND(NOT({BYPASS_FLOWS}), ISPICKVAL({{!$Record.Reason}}, &quot;Existing problem&quot;))</filterFormula>
        <object>Case</object>
        <recordTriggerType>Create</recordTriggerType>
        <triggerType>RecordBeforeSave</triggerType>
    </start>
    <status>Active</status>
</Flow>
""",
}

if __name__ == "__main__":
    for name, body in CLASSES.items():
        apex_class(name, body)
    for name, body in TRIGGERS.items():
        apex_trigger(name, body)
    for name, body in FLOWS.items():
        write(f"flows/{name}.flow-meta.xml", body)
    print("apex, triggers and flows generated")
