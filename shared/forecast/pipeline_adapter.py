"""Build legacy pipeline input from validated computed probabilities."""
from .core import validate,derive,digest


def pipeline_input(record):
    validate(record)
    if record["status"]=="unmodeled" or record["confidence"] is None:
        raise ValueError("computed pipeline input requires probabilities and confidence")
    d=derive(record["score_distribution"])
    groups=[{"id":"main_scores","label":"比分主分布","outcomes":[
        {"key":"score_"+key.replace("-","_"),"label":key,"probability":p*100}
        for key,p in record["score_distribution"].items()]},
        {"id":"winner","label":"勝負","outcomes":[
            {"key":"winner_"+key,"label":"和局" if key=="draw" else record["participants"][0 if key=="a" else 1],"probability":p*100}
            for key,p in d["winner_probabilities"].items()]}]
    return {"schema_version":"1.0","prediction_id":record["forecast_id"],"created_at":record["created_at"],
            "as_of":record["data_cutoff"],"sport":record["sport"],"mode":"full",
            "question":"依已計算主分布查核並解釋勝方、比分與主要限制。",
            "event":{"event_id":record["event_id"],"competition":record["competition"],
                     "start_time":record["scheduled_start"],"timezone":"Asia/Taipei",
                     "format":"BO"+str(record["best_of"]) if record.get("best_of") else record["scope"],
                     "participants":record["participants"]},
            "model_data":{"data_quality":{"completeness":record["confidence"]["components"]["data_completeness"],
                                          "missing":record["missing_data"],"warnings":["模型狀態："+record["status"]]},
                          "evidence":[{"id":e["id"],"category":"forecast_evidence","claim":e["claim"],"status":"reported",
                                       "source":{"title":e["id"],"url":e["url"],"published_at":e["available_at"],"retrieved_at":e["retrieved_at"]}}
                                      for e in record["evidence"]],
                          "notes":["來源快照 SHA-256："+digest(record),"重新估計機率需先重建 canonical forecast，再重跑管線。"],
                          "computed_probability_groups":groups},"market_data":[]}
