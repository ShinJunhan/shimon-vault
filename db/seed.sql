-- ─────────────────────────────────────────────────────────────
-- ShimonVault — Seed Data
-- Demo users for presentation.
-- Passwords are SHA-256-then-bcrypt hashed, matching auth.py's
-- hash_password() exactly (SHA-256 pre-hash works around bcrypt's
-- 72-byte input limit, then bcrypt hashes that digest).
-- Plain passwords: admin=Admin1234!, editor=Edit5678!, viewer=View9012!
-- ─────────────────────────────────────────────────────────────

INSERT INTO users (id, email, username, hashed_pw, role, is_active, suspended) VALUES
  ('00000000-0000-0000-0000-000000000001',
   'admin@shimonvault.com',
   'admin',
   '$2b$12$6JLE0FMUAqxJPVG0asQumePimHXf7py669pjlk789McpGc8zvWcIC',  -- Admin1234!
   'ADMIN', true, false),
  ('00000000-0000-0000-0000-000000000002',
   'editor@shimonvault.com',
   'editor',
   '$2b$12$18C5deO0IEASNyN1OTVSTe6jJRBkaJ.DidcWzA58OFfC3JcLEVFK.',  -- Edit5678!
   'EDITOR', true, false),
  ('00000000-0000-0000-0000-000000000003',
   'viewer@shimonvault.com',
   'viewer',
   '$2b$12$Jp2px1Tq74hPsJliSovWdO5pEb9piygmDAq387HMCRHm1ErjGi7z6',  -- View9012!
   'VIEWER', true, false)
ON CONFLICT DO NOTHING;
