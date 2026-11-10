/**
 * FinTech Agent — MongoDB Server-Side Authentication Rollback Script
 *
 * Usage with mongosh:
 *   mongosh "mongodb://<admin_user>:<admin_password>@localhost:27017/admin" scripts/rollback_mongo_auth.js
 *
 * This script drops provisioned users when reverting to unauthenticated mode.
 */

const adminDb = db.getSiblingDB("admin");
const bankingDb = db.getSiblingDB("fintech_agent_db");
const metadataDb = db.getSiblingDB("agent_metadata_db");

print("[ROLLBACK] Initiating rollback of provisioned MongoDB users...");

try {
  if (bankingDb.getUser("fintech_reader")) {
    bankingDb.dropUser("fintech_reader");
    print("[OK] fintech_reader dropped from fintech_agent_db.");
  } else {
    print("[INFO] fintech_reader does not exist on fintech_agent_db.");
  }
} catch (e) {
  print("[WARN] Error dropping fintech_reader: " + e.message);
}

try {
  if (metadataDb.getUser("agent_metadata_writer")) {
    metadataDb.dropUser("agent_metadata_writer");
    print("[OK] agent_metadata_writer dropped from agent_metadata_db.");
  } else {
    print("[INFO] agent_metadata_writer does not exist on agent_metadata_db.");
  }
} catch (e) {
  print("[WARN] Error dropping agent_metadata_writer: " + e.message);
}

try {
  if (adminDb.getUser("adminUser")) {
    adminDb.dropUser("adminUser");
    print("[OK] adminUser dropped from admin.");
  } else {
    print("[INFO] adminUser does not exist on admin.");
  }
} catch (e) {
  print("[WARN] Error dropping adminUser: " + e.message);
}

print("[COMPLETED] User rollback finished.");
print("[NEXT STEPS] If reverting server configuration, disable security.authorization in mongod.cfg and restart MongoDB service.");
