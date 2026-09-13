"""Where suite_drift_threshold comes from.

Measures drift distribution under edits known to be harmless (H) and edits
known to change behaviour (S). The threshold is set in the gap between the two
medians, not guessed.
"""
import shutil, importlib, sys, os
sys.path.insert(0,os.getcwd())
from promptlock.runner import Config, check, record
from promptlock import store
APP="examples/demo_app/app.py"; B="/tmp/cal_app.py"
shutil.copy(APP,B)
cfg=Config.load("promptlock.yaml"); store.save(record(cfg)); base=store.load()
STRICT="Respond with ONLY valid JSON. No prose, no markdown fence."
V={
 "H whitespace":("You are a support triage assistant.","You are a support triage assistant. "),
 "H synonym":("support triage assistant","support triage agent"),
 "H verb":("Classify the ticket below.","Categorise the ticket below."),
 "H article":("Classify the ticket below.","Classify the following ticket."),
 "H politeness":("Classify the ticket below.","Please classify the ticket below."),
 "H reorder":(STRICT,STRICT.replace("No prose, no markdown fence.","No markdown fence, no prose.")),
 "S urgency-bias":("a one-line summary.","a one-line summary.\nErr on the side of high urgency."),
 "S hedge":(STRICT,STRICT+"\nWhen unsure, classify as other."),
}
for n,(o,nw) in V.items():
    shutil.copy(B,APP); s=open(APP).read(); assert o in s,n; open(APP,"w").write(s.replace(o,nw,1))
    importlib.invalidate_caches()
    r=check(cfg,base); ds=sorted((c["drift"] for c in r["cases"].values()),reverse=True)
    print(f"{n:<18} max={ds[0]:.4f} p90={ds[5]:.4f} median={ds[25]:.4f}")
shutil.copy(B,APP)
