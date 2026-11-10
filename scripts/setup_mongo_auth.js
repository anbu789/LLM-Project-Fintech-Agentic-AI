/**
 * FinTech Agent — MongoDB Server-Side Authentication Setup Script
 *
 * Usage with mongosh:
 *   mongosh mongodb://localhost:27017/ scripts/setup_mongo_auth.js
 *
 * This script idempotently creates:
 * 1. An administrative user on the 'admin' database.
 * 2. A least-privilege read-only user on 'fintech_agent_db'.
 * 3. A least-privilege read-write user on 'agent_metadata_db'.
 */

// 1. Create Administrator on 'admin'
const adminDb = db.getSiblingDB("admin");
const adminExists = adminDb.getUser("adminUser");
if (!adminExists) {
  print("Creating administrative user 'adminUser' on 'admin' database...");
  adminDb.createUser({
    user: "adminUser",
    pwd: "AdminSecurePassword2026!",
    roles: [
      { role: "userAdminAnyDatabase", db: "admin" },
      { role: "readWriteAnyDatabase", db: "admin" }
    ]
  });
  print("[OK] adminUser created successfully on 'admin'.");
} else {
  print("[INFO] adminUser already exists on 'admin' database.");
}

// 2. Create Read-Only User on 'fintech_agent_db'
const bankingDb = db.getSiblingDB("fintech_agent_db");
const readerExists = bankingDb.getUser("fintech_reader");
if (!readerExists) {
  print("Creating read-only user 'fintech_reader' on 'fintech_agent_db'...");
  bankingDb.createUser({
    user: "fintech_reader",
    pwd: "FintechReaderPass2026!",
    roles: [
      { role: "read", db: "fintech_agent_db" }
    ]
  });
  print("[OK] fintech_reader created successfully on 'fintech_agent_db'.");
} else {
  print("[INFO] fintech_reader already exists on 'fintech_agent_db'.");
}

// 3. Create Read-Write Metadata User on 'agent_metadata_db'
const metadataDb = db.getSiblingDB("agent_metadata_db");
const writerExists = metadataDb.getUser("agent_metadata_writer");
if (!writerExists) {
  print("Creating metadata user 'agent_metadata_writer' on 'agent_metadata_db'...");
  metadataDb.createUser({
    user: "agent_metadata_writer",
    pwd: "AgentMetadataWriterPass2026!",
    roles: [
      { role: "readWrite", db: "agent_metadata_db" }
    ]
  });
  print("[OK] agent_metadata_writer created successfully on 'agent_metadata_db'.");
} else {
  print("[INFO] agent_metadata_writer already exists on 'agent_metadata_db'.");
}

print("Authentication setup complete. Next step: configure security.authorization in mongod.cfg and restart MongoDB service.");
