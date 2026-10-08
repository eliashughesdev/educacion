# Auth testing playbook
1. mongosh → `use test_database` → `db.users.findOne({role:"superadmin"})` — hash must start with `$2b$`; indexes users.email unique, login_attempts.identifier, sessions.jti.
2. `curl -c cookies.txt -X POST $URL/api/auth/login -H "Content-Type: application/json" -d '{"email":"eliasflotahughes@gmail.com","password":"SchoolERP#2026!"}'`
3. `curl -b cookies.txt $URL/api/auth/me` returns the same user with `permissions`.
4. 5 wrong passwords from same IP+email → 429 lockout for 15 minutes.
5. POST /api/auth/refresh rotates refresh token; reusing an old refresh token → 401 and revokes all sessions of the user.
