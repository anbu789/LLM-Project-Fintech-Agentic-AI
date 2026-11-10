/**
 * FinTech Agent — MongoDB Server-Side Authentication Rollback Script
 *
 * Usage with mongosh:
 *   mongosh mongodb://adminUser:AdminSecurePassword2026!@localhost:27017/admin scripts/rollback_mongo_auth.js
 *
 * This script drops created users if reverting to unauthenticated mode.
 */

const adminDb = db.getSiblingDB("admin");
const bankingDb = db.getSiblingDB("fintech_agent_db");
const metadataDb = db.getSiblingDB("agent_metadata_db");

print("Rolling back users...");

try {
  if (bankingDb.getUser("fintech_reader")) {
    bankingDb.dropUser("fintech_reader");
    print("[OK] fintech_reader dropped from fintech_agent_db.");
  }
} catch (e) {
  print("[WARN] Error dropping fintech_reader: " + e);
}

try {
  if (metadataDb.getUser("agent_metadata_writer")) {
    metadataDb.dropUser("agent_metadata_writer");
    print("[OK] agent_metadata_writer dropped from agent_metadata_db.");
  }
} catch (e) {
  print("[WARN] Error dropping agent_metadata_writer: " + e);
}

try {
  if (adminDb.getUser("adminUser")) {
    adminDb.dropUser("adminUser");
    print("[OK] adminUser dropped from admin.");
  }
} catch (e) {
  print("[WARN] Error dropping adminUser: " + e);
}

print("Rollback complete. If reverting server configuration, disable security.authorization in mongod.cfg and restart MongoDB service.");
