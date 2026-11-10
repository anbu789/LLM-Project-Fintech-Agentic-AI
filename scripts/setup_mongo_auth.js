/**
 * FinTech Agent — MongoDB Server-Side Authentication Setup Script
 *
 * Usage with mongosh:
 *   BANKING_DB_PASSWORD="<pwd>" METADATA_DB_PASSWORD="<pwd>" [ADMIN_DB_PASSWORD="<pwd>"] \
 *   mongosh mongodb://localhost:27017/ scripts/setup_mongo_auth.js
 *
 * NOTE: For standard deployment, use scripts/mongo_init_auth.js.
 */

// Delegate directly to the hardened mongo_init_auth.js logic
load("scripts/mongo_init_auth.js");
