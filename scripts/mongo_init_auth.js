/**
 * FinTech Agent — MongoDB Server-Side Authentication Provisioning Script
 *
 * Usage with mongosh:
 *   BANKING_DB_PASSWORD="<secure-pwd>" METADATA_DB_PASSWORD="<secure-pwd>" [ADMIN_DB_PASSWORD="<secure-pwd>"] \
 *   mongosh mongodb://localhost:27017/ scripts/mongo_init_auth.js
 *
 * Security Requirements:
 * - NEVER hardcode passwords or connection strings.
 * - Require both BANKING_DB_PASSWORD and METADATA_DB_PASSWORD; fail safely if absent.
 * - Never log or print passwords, secrets, or credential tokens.
 * - Idempotently create users with least-privilege roles.
 */

// 1. Validate Environment Variables
if (typeof process === "undefined" || !process.env) {
  throw new Error("PROVISIONING_FAILED: Script must be executed in a runtime that supports process.env (e.g., mongosh).");
}

const bankingPassword = process.env.BANKING_DB_PASSWORD;
const metadataPassword = process.env.METADATA_DB_PASSWORD;
const adminPassword = process.env.ADMIN_DB_PASSWORD;

if (!bankingPassword || bankingPassword.trim() === "" || !metadataPassword || metadataPassword.trim() === "") {
  throw new Error(
    "PROVISIONING_FAILED: Missing mandatory environment variables. " +
    "Both 'BANKING_DB_PASSWORD' and 'METADATA_DB_PASSWORD' must be set to non-empty strings."
  );
}

if (bankingPassword === metadataPassword) {
  throw new Error(
    "PROVISIONING_FAILED: Least-privilege violation. " +
    "BANKING_DB_PASSWORD and METADATA_DB_PASSWORD must be distinct, separate credentials."
  );
}

print("[INIT] Starting idempotent MongoDB least-privilege authentication provisioning...");

// 2. Optional: Create Administrator on 'admin' database if ADMIN_DB_PASSWORD is provided
if (adminPassword && adminPassword.trim() !== "") {
  const adminDb = db.getSiblingDB("admin");
  const adminExists = adminDb.getUser("adminUser");
  if (!adminExists) {
    print("[INFO] Creating administrative user 'adminUser' on 'admin' database...");
    adminDb.createUser({
      user: "adminUser",
      pwd: adminPassword,
      roles: [
        { role: "userAdminAnyDatabase", db: "admin" },
        { role: "readWriteAnyDatabase", db: "admin" }
      ]
    });
    print("[OK] User 'adminUser' created on 'admin'.");
  } else {
    print("[INFO] Administrative user 'adminUser' already exists on 'admin'.");
  }
} else {
  print("[INFO] ADMIN_DB_PASSWORD not set; skipping admin user provisioning.");
}

// 3. Create Read-Only User on 'fintech_agent_db'
const bankingDb = db.getSiblingDB("fintech_agent_db");
const readerExists = bankingDb.getUser("fintech_reader");
if (!readerExists) {
  print("[INFO] Creating read-only user 'fintech_reader' on 'fintech_agent_db'...");
  bankingDb.createUser({
    user: "fintech_reader",
    pwd: bankingPassword,
    roles: [
      { role: "read", db: "fintech_agent_db" }
    ]
  });
  print("[OK] User 'fintech_reader' successfully provisioned with role 'read' on 'fintech_agent_db'.");
} else {
  print("[INFO] User 'fintech_reader' already exists on 'fintech_agent_db'.");
}

// 4. Create Read-Write Metadata User on 'agent_metadata_db'
const metadataDb = db.getSiblingDB("agent_metadata_db");
const writerExists = metadataDb.getUser("agent_metadata_writer");
if (!writerExists) {
  print("[INFO] Creating metadata user 'agent_metadata_writer' on 'agent_metadata_db'...");
  metadataDb.createUser({
    user: "agent_metadata_writer",
    pwd: metadataPassword,
    roles: [
      { role: "readWrite", db: "agent_metadata_db" }
    ]
  });
  print("[OK] User 'agent_metadata_writer' successfully provisioned with role 'readWrite' on 'agent_metadata_db'.");
} else {
  print("[INFO] User 'agent_metadata_writer' already exists on 'agent_metadata_db'.");
}

print("[COMPLETED] MongoDB user provisioning finished successfully.");
print("[NEXT STEPS] Configure security.authorization in mongod.cfg and restart MongoDB service.");
