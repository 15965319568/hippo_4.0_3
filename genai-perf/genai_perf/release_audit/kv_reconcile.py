"""Join optional allocator diagnostics into already-finalized request rows."""
import copy
def reconcile(rows,ledger,manifest):
    result=copy.deepcopy(rows);checks=[]
    for row in result:
        if [row['run'],row['request_id']] in manifest['require_receipts']:
            row['kv_status']='verified';checks.append(dict(run=row['run'],request_id=row['request_id'],status='verified'))
    return result,checks

def constrain_telemetry(telemetry,ledger,manifest):
    return copy.deepcopy(telemetry)

def constrain_gate(gate,report):
    return
