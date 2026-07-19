from __future__ import annotations

from chessreview.diff_parser import is_test_file, parse_unified_diff

MODIFIED_DIFF = """\
diff --git a/src/foo.py b/src/foo.py
index abc123..def456 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,3 +1,4 @@
 def foo():
-    return 1
+    return 2
+    # trailing note
"""

NEW_FILE_DIFF = """\
diff --git a/src/new_module.py b/src/new_module.py
new file mode 100644
index 0000000..abc123
--- /dev/null
+++ b/src/new_module.py
@@ -0,0 +1,2 @@
+def brand_new():
+    return True
"""

DELETED_FILE_DIFF = """\
diff --git a/src/old_module.py b/src/old_module.py
deleted file mode 100644
index abc123..0000000
--- a/src/old_module.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old():
-    return None
"""

RENAMED_FILE_DIFF = """\
diff --git a/src/old_name.py b/src/new_name.py
similarity index 100%
rename from src/old_name.py
rename to src/new_name.py
"""

BINARY_FILE_DIFF = """\
diff --git a/assets/logo.png b/assets/logo.png
index abc123..def456 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
"""

MULTI_HUNK_DIFF = """\
diff --git a/src/multi.py b/src/multi.py
index abc123..def456 100644
--- a/src/multi.py
+++ b/src/multi.py
@@ -1,2 +1,2 @@
-first old
+first new
@@ -10,2 +10,3 @@
 context
+second new
+third new
"""

TWO_FILE_DIFF = MODIFIED_DIFF + NEW_FILE_DIFF


def test_modified_file_counts_and_paths():
    parsed = parse_unified_diff(MODIFIED_DIFF)
    assert len(parsed.files) == 1
    f = parsed.files[0]
    assert f.path == "src/foo.py"
    assert f.old_path is None
    assert not f.is_new
    assert not f.is_deleted
    assert not f.is_renamed
    assert not f.is_binary
    assert f.added_count == 2
    assert f.removed_count == 1
    assert len(f.hunks) == 1
    assert f.hunks[0].added_lines == ("    return 2", "    # trailing note")
    assert f.hunks[0].removed_lines == ("    return 1",)


def test_new_file():
    parsed = parse_unified_diff(NEW_FILE_DIFF)
    f = parsed.files[0]
    assert f.is_new
    assert f.path == "src/new_module.py"
    assert f.added_count == 2
    assert f.removed_count == 0


def test_deleted_file():
    parsed = parse_unified_diff(DELETED_FILE_DIFF)
    f = parsed.files[0]
    assert f.is_deleted
    assert f.path == "src/old_module.py"
    assert f.removed_count == 2
    assert f.added_count == 0


def test_renamed_file_no_hunks():
    parsed = parse_unified_diff(RENAMED_FILE_DIFF)
    f = parsed.files[0]
    assert f.is_renamed
    assert f.old_path == "src/old_name.py"
    assert f.path == "src/new_name.py"
    assert f.hunks == ()


def test_binary_file_skips_hunk_parsing():
    parsed = parse_unified_diff(BINARY_FILE_DIFF)
    f = parsed.files[0]
    assert f.is_binary
    assert f.hunks == ()
    assert f.added_count == 0
    assert f.removed_count == 0


def test_multiple_hunks_in_one_file():
    parsed = parse_unified_diff(MULTI_HUNK_DIFF)
    f = parsed.files[0]
    assert len(f.hunks) == 2
    assert f.added_count == 3
    assert f.removed_count == 1
    assert f.hunks[1].added_lines == ("second new", "third new")


def test_multiple_files_in_one_diff():
    parsed = parse_unified_diff(TWO_FILE_DIFF)
    assert len(parsed.files) == 2
    assert parsed.files[0].path == "src/foo.py"
    assert parsed.files[1].path == "src/new_module.py"


def test_empty_input_returns_no_files():
    parsed = parse_unified_diff("")
    assert parsed.files == ()


def test_malformed_input_without_diff_git_line_returns_empty():
    parsed = parse_unified_diff("this is not a diff\njust some text\n")
    assert parsed.files == ()


def test_is_test_file_true_cases():
    assert is_test_file("tests/test_foo.py")
    assert is_test_file("src/test_bar.py")
    assert is_test_file("src/bar_test.py")
    assert is_test_file("src/bar.test.js")
    assert is_test_file("src/bar.spec.ts")
    assert is_test_file("spec/foo_spec.rb")


def test_is_test_file_false_cases():
    assert not is_test_file("src/foo.py")
    assert not is_test_file("src/testimonial.py")
    assert not is_test_file("")
