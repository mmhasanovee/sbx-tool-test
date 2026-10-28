/**
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
