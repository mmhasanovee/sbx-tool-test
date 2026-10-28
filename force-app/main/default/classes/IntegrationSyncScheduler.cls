/**
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
