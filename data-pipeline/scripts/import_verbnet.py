"""Import VerbNet selective data (classes, roles, examples - skip syntactic frames)."""
import sqlite3

from utils import SQLUNET_DB, LEXICON_V2


def import_classes(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import VerbNet classes."""
    print("Importing VerbNet classes...")
    cursor = src.execute("SELECT classid, class FROM vn_classes")
    rows = [(row[0], row[1], None) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO vn_classes (class_id, class_name, class_definition) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} classes")


def import_class_members(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import class membership (verb -> class links with synset mapping)."""
    print("Importing class memberships...")
    # vn_members_senses has the synsetid link we need
    cursor = src.execute("""
        SELECT wordid, synsetid, classid, vnwordid
        FROM vn_members_senses
        WHERE synsetid IS NOT NULL
    """)
    rows = [(row[0], str(row[1]), row[2], row[3]) for row in cursor]
    dst.executemany(
        "INSERT OR IGNORE INTO vn_class_members (wordid, synsetid, classid, vnwordid) VALUES (?, ?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} memberships")


def import_roles(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import theta roles per class."""
    print("Importing theta roles...")
    # Join with roletypes to get the role name
    cursor = src.execute("""
        SELECT r.roleid, r.classid, rt.roletype
        FROM vn_roles r
        JOIN vn_roletypes rt ON rt.roletypeid = r.roletypeid
    """)
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO vn_roles (role_id, class_id, theta_role) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} roles")


def import_examples(src: sqlite3.Connection, dst: sqlite3.Connection):
    """Import usage examples linked to classes via frames."""
    print("Importing examples...")
    # Examples link to frames, frames link to classes
    # Get unique class-example pairs
    cursor = src.execute("""
        SELECT DISTINCT e.exampleid, cf.classid, e.example
        FROM vn_examples e
        JOIN vn_frames_examples fe ON fe.exampleid = e.exampleid
        JOIN vn_classes_frames cf ON cf.frameid = fe.frameid
    """)
    rows = list(cursor)
    dst.executemany(
        "INSERT OR IGNORE INTO vn_examples (example_id, class_id, example_text) VALUES (?, ?, ?)",
        rows
    )
    print(f"  Imported {len(rows)} examples")


def main():
    if not SQLUNET_DB.exists():
        raise FileNotFoundError(f"Source DB not found: {SQLUNET_DB}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Target DB not found: {LEXICON_V2}")

    src = sqlite3.connect(SQLUNET_DB)
    dst = sqlite3.connect(LEXICON_V2)

    import_classes(src, dst)
    import_class_members(src, dst)
    import_roles(src, dst)
    import_examples(src, dst)

    dst.commit()
    src.close()
    dst.close()
    print("VerbNet import complete!")


if __name__ == "__main__":
    main()
