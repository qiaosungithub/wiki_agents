import asyncio
from xmanager import xm
from xmanager import xm_abc

async def main():
    exp = xm_abc.get_experiment(experiment_id=274485633)
    work_units = await exp.get_work_units()
    for wu in work_units:
        print(f"Work unit {wu.id} status: {wu.status}")

asyncio.run(main())
