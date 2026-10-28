/**
 * Assigns Region__c on accounts from their billing country.
 */
public with sharing class AccountRegionService {
    public static void assignRegions(List<Account> accounts) {
        Set<String> countries = new Set<String>();
        for (Account acc : accounts) {
            if (acc.Region__c == null && String.isNotBlank(acc.BillingCountry)) {
                countries.add(acc.BillingCountry);
            }
        }
        if (countries.isEmpty()) {
            return;
        }
        Map<String, Id> regionByCountry = new Map<String, Id>();
        for (Region__c region : [SELECT Id, Country__c FROM Region__c WHERE Country__c IN :countries WITH SYSTEM_MODE]) {
            regionByCountry.put(region.Country__c, region.Id);
        }
        for (Account acc : accounts) {
            if (acc.Region__c == null && regionByCountry.containsKey(acc.BillingCountry)) {
                acc.Region__c = regionByCountry.get(acc.BillingCountry);
            }
        }
    }
}
