/**
 * Hard-coded integration base URLs. Kept on purpose to test whether a sandbox tool swaps URLs inside Apex code.
 */
public with sharing class SbxEndpoints {
    public static final String ERP_BASE_URL = 'https://erp.example.com';
    public static final String PAYMENTS_BASE_URL = 'https://payments.example.com';

    public static String erpUrl(String path) {
        return ERP_BASE_URL + path;
    }
}
