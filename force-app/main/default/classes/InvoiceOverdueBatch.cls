/**
 * Nightly job: marks sent invoices past their due date as Overdue.
 */
public with sharing class InvoiceOverdueBatch implements Database.Batchable<SObject>, Schedulable {
    public Database.QueryLocator start(Database.BatchableContext context) {
        return Database.getQueryLocator(
            'SELECT Id FROM Invoice__c WHERE Status__c = \'Sent\' AND Due_Date__c < TODAY',
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
