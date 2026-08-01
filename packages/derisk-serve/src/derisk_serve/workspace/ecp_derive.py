"""场景空间 -> ECP workspace 派生约定。

ECP 无 workspace 表,workspace_id 只是各表上的字符串作用域列。每个场景空间
按纯函数派生专属 ECP workspace_id,无需存储映射、无需供给(惰性即存在)。
``default`` 保留为全局共享语义库。
"""


def derived_ecp_workspace_id(workspace_code: str) -> str:
    """由场景空间 workspace_code 派生专属 ECP workspace_id。

    用 ``ecp_`` 而非 ``ws_`` 前缀:自动生成的 workspace_code 本身已是
    ``ws_<uuid12>``,再叠 ``ws_`` 会得到 ``ws_ws_xxx``;且与 ECP 软知识空间
    slug 约定 ``ecp-<workspace_id>`` 同族。
    """
    return f"ecp_{workspace_code}"
