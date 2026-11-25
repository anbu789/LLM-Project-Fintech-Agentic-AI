/**
 * ==============================================================================
 * DANGER: DEVELOPMENT / LOCAL TEST CLEANUP ONLY — DO NOT USE IN PRODUCTION
 * ==============================================================================
 * FinTech Agent — MongoDB Server-Side Authentication Rollback Script
 *
 * This script drops all provisioned MongoDB users (fintech_reader,
 * agent_metadata_writer, adminUser) and reverts the database to unauthenticated
 * state. It is strictly intended for local developer teardown and automated test
 * fixtures. NEVER run this script in staging or production environments.
 *
 * Usage with mongosh:
 *   mongosh "mongodb://<admin_user>:<admin_password>@localhost:27017/admin" scripts/rollback_mongo_auth.js
 * ==============================================================================
 */

const adminDb = db.getSiblingDB("admin");
const bankingDb = db.getSiblingDB("fintech_agent_db");
const metadataDb = db.getSiblingDB("agent_metadata_db");

print("[ROLLBACK] Initiating rollback of provisioned MongoDB users...");

try {
  ["fintech_readonly_user", "fintech_reader"].forEach(u => {
    if (bankingDb.getUser(u)) {
      bankingDb.dropUser(u);
      print(`[OK] ${u} dropped from fintech_agent_db.`);
    }
  });
} catch (e) {
  print("[WARN] Error dropping banking read-only users: " + e.message);
}

try {
  ["agent_metadata_user", "agent_metadata_writer"].forEach(u => {
    if (metadataDb.getUser(u)) {
      metadataDb.dropUser(u);
      print(`[OK] ${u} dropped from agent_metadata_db.`);
    }
  });
} catch (e) {
  print("[WARN] Error dropping metadata users: " + e.message);
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
