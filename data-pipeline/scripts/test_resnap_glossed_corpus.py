import sys, json
from pathlib import Path
sys.path.insert(0, "scripts")
from resnap_glossed_corpus import resnap_file

def test_resnap_file_writes_and_counts(tmp_path):
    inp = tmp_path/"in.jsonl"; out = tmp_path/"out.jsonl"
    rec={"schema_version":"chain.v1","topic":"t","topic_synset_id":"1","vehicle":"v",
         "vehicle_synset_id":"9","proposer":"p","round":3,"chain_signature":"a"*64,
         "generated_at":"x","chain":[
           {"phrase":"t","head":"t","synset_id":"1","gloss":"tg"},
           {"phrase":"v","head":"v","synset_id":"9","gloss":"vg"}]}
    inp.write_text(json.dumps(rec)+"\n\n")  # blank line tolerated
    res = resnap_file(str(inp), str(out), lambda h,g: "9new" if h=="v" else None)
    assert res["records"]==1 and res["vehicle_changed"]==1
    o=json.loads(out.read_text().splitlines()[0])
    assert o["vehicle_synset_id"]=="9new"
    assert o["chain_signature"]=="a"*64
