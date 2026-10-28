/**
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
