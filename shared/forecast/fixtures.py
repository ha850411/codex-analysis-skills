"""Synthetic examples only; never use these observations for real predictions."""

def event(sport="lol"):
    return {"event_id":f"demo-{sport}","sport":sport,"competition":"合成排版示例（非真實預測）",
            "snapshot":"pre-match","created_at":"2020-03-01T10:00:00+08:00",
            "data_cutoff":"2020-03-01T09:00:00+08:00","scheduled_start":"2020-03-01T18:00:00+08:00",
            "participants":["Example A","Example B"],"scope":"90-minutes" if sport=="soccer" else "full-game",
            "best_of":3 if sport in {"lol","cs","valorant","dota2"} else None,"confidence":{"value":60,"components":{k:60 for k in (
                "data_completeness","freshness","lineup_certainty","regime_relevance","model_stability")}},
            "evidence":[{"id":"fixture","url":"https://example.invalid/fixture","claim":"合成測試資料，不能用於真實賽事",
                         "available_at":"2020-03-01T08:00:00+08:00","retrieved_at":"2020-03-01T09:00:00+08:00"}]}


def history(sport="lol"):
    scores=[[2,1],[0,2],[2,0],[1,2]]
    if sport=="nba": scores=[[110,105],[99,106],[125,115],[100,101]]
    if sport=="mlb": scores=[[5,2],[1,4],[6,3],[2,4]]
    if sport=="soccer": scores=[[2,1],[0,0],[3,1],[0,2]]
    return [{"event_id":f"h-{i}","sport":sport,"participants":["Example A","Example B"],
             "score":scores[i%4],"completed_at":f"2020-02-{i+1:02d}T20:00:00+08:00",
             "available_at":f"2020-02-{i+1:02d}T20:10:00+08:00","result_status":"final",
             "source_url":"https://example.invalid/result","home_index":1} for i in range(20)]
