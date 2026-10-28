// Schedules the production jobs that a sandbox refresh should abort or reschedule.
Set<String> existing = new Set<String>();
for (CronTrigger job : [SELECT CronJobDetail.Name FROM CronTrigger WHERE CronJobDetail.Name LIKE 'SBX %']) {
    existing.add(job.CronJobDetail.Name);
}
if (!existing.contains('SBX Invoice Overdue Nightly')) {
    System.schedule('SBX Invoice Overdue Nightly', '0 0 2 * * ?', new InvoiceOverdueBatch());
}
if (!existing.contains('SBX Integration Sync Hourly')) {
    System.schedule('SBX Integration Sync Hourly', '0 0 * * * ?', new IntegrationSyncScheduler());
}
