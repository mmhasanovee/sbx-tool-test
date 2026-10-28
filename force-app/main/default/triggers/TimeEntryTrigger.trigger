trigger TimeEntryTrigger on Time_Entry__c (before insert, before update) {
    if (AutomationSettings.bypassTriggers()) {
        return;
    }
    TimeEntryService.blockClosedWorkPackages(Trigger.new);
}
