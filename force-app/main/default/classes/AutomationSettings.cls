/**
 * Reads the Automation_Settings__c bypass switches used by triggers, flows and validation rules.
 */
public with sharing class AutomationSettings {
    public static Boolean bypassTriggers() {
        Automation_Settings__c settings = Automation_Settings__c.getInstance();
        return settings != null && (settings.Bypass_All__c == true || settings.Bypass_Triggers__c == true);
    }
}
