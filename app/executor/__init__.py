"""SQL Executor layer — dry-run now, MaxCompute later.

MockExecutor:      validates SQL syntax, returns placeholder results.
MaxComputeExecutor: DataWorks ODPS read-only (future, needs endpoint).

All executors implement ExecutorClient from app.model_clients.
"""
