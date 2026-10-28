trigger CaseTrigger on Case (after insert) {
    if (AutomationSettings.bypassTriggers()) {
        return;
    }
    System.enqueueJob(new ErpCaseSyncJob(Trigger.newMap.keySet()));
}
