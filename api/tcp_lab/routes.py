"""
HTTP endpoints of the TCP Congestion Control Lab.

  GET  /api/tcp-lab/scenarios                          scenarios, variants, which results exist
  GET  /api/tcp-lab/results/{scenario}                 simulator + Mininet summaries
  GET  /api/tcp-lab/results/{scenario}/{variant}/timeseries?run=1
  GET  /api/tcp-lab/analysis                           Phase 5 analysis.json
  GET  /api/tcp-lab/analysis/plots                     names of the analysis PNGs
  GET  /api/tcp-lab/analysis/plots/{name}              one PNG
  POST /api/tcp-lab/live/simulate                      stream a simulator run over /ws/events
  POST /api/tcp-lab/live/replay                        stream a recorded Mininet run
  GET  /api/tcp-lab/live                               status of the live run
  POST /api/tcp-lab/live/stop                          stop it

Unknown names give 404; the frontend only displays what these return.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from api.tcp_lab import results
from api.tcp_lab.live import live_runner
from api.tcp_lab.models import ReplayRequest, SimulateRequest

router = APIRouter(prefix="/api/tcp-lab", tags=["tcp-lab"])


def not_found(error):
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get("/scenarios")
async def get_scenarios():
    return results.list_scenarios()


@router.get("/results/{scenario_id}")
async def get_scenario_results(scenario_id: str):
    try:
        return results.scenario_results(scenario_id)
    except ValueError as error:
        raise not_found(error)


@router.get("/results/{scenario_id}/{variant}/timeseries")
async def get_variant_timeseries(scenario_id: str, variant: str, run: int = 1):
    try:
        return results.variant_timeseries(scenario_id, variant, mininet_run=run)
    except ValueError as error:
        raise not_found(error)


@router.get("/analysis")
async def get_analysis():
    data = results.analysis()
    if data is None:
        raise not_found("No analysis yet: run `python -m tcp_lab.run_analysis`")
    return data


@router.get("/analysis/plots")
async def get_analysis_plot_names():
    return results.analysis_plot_names()


@router.get("/analysis/plots/{name}")
async def get_analysis_plot(name: str):
    try:
        return FileResponse(results.analysis_plot_path(name), media_type="image/png")
    except ValueError as error:
        raise not_found(error)


@router.post("/live/simulate")
async def start_live_simulation(request: SimulateRequest):
    try:
        return await live_runner.start_simulation(request.scenario, request.variant,
                                                  request.algorithms, request.seed, request.speed)
    except ValueError as error:
        raise not_found(error)


@router.post("/live/replay")
async def start_live_replay(request: ReplayRequest):
    try:
        return await live_runner.start_replay(request.scenario, request.variant,
                                              request.run, request.speed)
    except ValueError as error:
        raise not_found(error)


@router.get("/live")
async def get_live_status():
    return live_runner.get_status()


@router.post("/live/stop")
async def stop_live_run():
    stopped = await live_runner.stop()
    return {"stopped": stopped, "status": live_runner.get_status()}
