"""示例的外部 MCP 服务：把 销售.xlsx 装进内存 SQLite，给 agent 只读 SQL 查询。
真业务换成连 MySQL / PostgreSQL 的只读账号即可；在 mcp.json 里登记，agent 就多了 mcp__sales_db__* 工具。
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd
from mcp.server.mcpserver import MCPServer

库 = sqlite3.connect(":memory:", check_same_thread=False)
pd.read_excel(Path(__file__).resolve().parents[1] / "数据" / "销售.xlsx").to_sql("销售", 库, index=False)
server = MCPServer("sales_db", instructions="销售明细库，只读。表：销售(订单号,日期,地区,门店,商品,数量,单价,金额,会员)。")


@server.tool(name="list_tables", description="列出所有表和列。")
def 列表() -> dict:
    return {t: [c[1] for c in 库.execute(f'pragma table_info("{t}")')]
            for (t,) in 库.execute("select name from sqlite_master where type='table'")}


@server.tool(name="sql_query", description="只读 SQL（只允许 SELECT / WITH），最多返回 200 行。")
def 查(sql: str) -> dict:
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or re.search(r";\s*\S", sql):
        raise ValueError("只允许单条 SELECT / WITH 查询")
    游标 = 库.execute(sql)
    列 = [d[0] for d in 游标.description]
    行 = 游标.fetchmany(200)
    return {"列": 列, "行": [list(r) for r in 行], "行数": len(行)}


if __name__ == "__main__":
    server.run()
