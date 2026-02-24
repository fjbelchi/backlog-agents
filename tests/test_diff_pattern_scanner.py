# tests/test_diff_pattern_scanner.py
import subprocess, json, sys, os, tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "../scripts/implementer/diff_pattern_scanner.py")

AUTH_DIFF = """+const token = jwt.sign({ userId }, process.env.JWT_SECRET);
+await bcrypt.hash(password, 10);
"""
CLEAN_DIFF = """+const greeting = "hello world";
+console.log(greeting);
"""
DB_DIFF = """+await db.createIndex({ field: 'userId' });
+await runMigration('add_users_table');
"""

def scan(diff_text):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.diff', delete=False) as f:
        f.write(diff_text)
        path = f.name
    r = subprocess.run([sys.executable, SCRIPT, "--diff", path], capture_output=True, text=True)
    os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)

def test_detects_auth_patterns():
    result = scan(AUTH_DIFF)
    assert "auth" in result["detected"]
    assert result["requires_high_risk_review"] is True

def test_clean_diff_no_review():
    result = scan(CLEAN_DIFF)
    assert result["detected"] == []
    assert result["requires_high_risk_review"] is False

def test_detects_db_schema():
    result = scan(DB_DIFF)
    assert "db_schema" in result["detected"]
    assert result["requires_high_risk_review"] is True

def test_multiple_patterns_detected():
    result = scan(AUTH_DIFF + DB_DIFF)
    assert "auth" in result["detected"]
    assert "db_schema" in result["detected"]
