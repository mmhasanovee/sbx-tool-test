@IsTest
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

    @IsTest
    static void buildsErpUrl() {
        Assert.areEqual('https://erp.example.com/cases', SbxEndpoints.erpUrl('/cases'));
    }

    @IsTest
    static void postCopyLogsSandboxName() {
        Test.testSandboxPostCopyScript(new SbxPostCopy(), UserInfo.getOrganizationId(), UserInfo.getOrganizationId(), 'SBXTEST');

        Assert.areEqual('POSTCOPY SBXTEST', [SELECT Payload__c FROM Integration_Log__c WITH SYSTEM_MODE LIMIT 1].Payload__c);
    }
}
