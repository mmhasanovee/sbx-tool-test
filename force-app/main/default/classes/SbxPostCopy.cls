/**
 * Runs once in a new or refreshed sandbox and logs which sandbox it ran in.
 */
public with sharing class SbxPostCopy implements SandboxPostCopy {
    public void runApexClass(SandboxContext context) {
        insert as system new Integration_Log__c(
            Direction__c = 'Inbound',
            Endpoint__c = 'SandboxPostCopy',
            Status_Code__c = 200,
            Payload__c = 'POSTCOPY ' + context.sandboxName(),
            Logged_At__c = System.now()
        );
    }
}
