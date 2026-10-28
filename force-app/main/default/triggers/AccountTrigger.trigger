trigger AccountTrigger on Account (before insert, before update) {
    if (AutomationSettings.bypassTriggers()) {
        return;
    }
    AccountRegionService.assignRegions(Trigger.new);
}
