"""
Light-weight wrapper so you can also start the optimiser with

    python -m optimiser

or

    python optimiser/main_async.py
"""
from optimiser_builder import main          # re-use the builder entry-point

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
