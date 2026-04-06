from .console_patch import (
    ConsoleCommandError,
    ConsoleCommandResult,
    ConsolePatchContext,
    compile_console_command,
)
from .loader import (
    LoadedUi,
    UiLayoutError,
    build_ui_runtime,
    load_layout_document,
    load_node_meta_dir,
    load_ui,
)
from .patch_engine import (
    PatchApplyResult,
    apply_patch_ops,
)
from .patch_ops import (
    AddNodeOp,
    MoveNodeOp,
    PatchOp,
    RemoveNodeOp,
    RenameNodeOp,
    ResizeNodeOp,
    SetNodeRectOp,
    UpdateNodeMetaOp,
)
from .persistence import (
    save_layout_document,
    save_node_meta_dir,
    save_ui,
)
from .render import (
    UtfRenderResult,
    render_utf_runtime,
)
from .schema import (
    LayoutDocument,
    LayoutNode,
    NlpMeta,
    NodeMeta,
    Rect,
    ScreenSpec,
    SnapLink,
    UiNode,
    UiRuntime,
)


# ════════════════════════════════════════
# RAW DISASSEMBLY (for manual reconstruction)
# ════════════════════════════════════════
#   0           RESUME                   0
# 
#   1           LOAD_SMALL_INT           1
#               LOAD_CONST               1 (('ConsoleCommandError', 'ConsoleCommandResult', 'ConsolePatchContext', 'compile_console_command'))
#               IMPORT_NAME              0 (console_patch)
#               IMPORT_FROM              1 (ConsoleCommandError)
#               STORE_NAME               1 (ConsoleCommandError)
#               IMPORT_FROM              2 (ConsoleCommandResult)
#               STORE_NAME               2 (ConsoleCommandResult)
#               IMPORT_FROM              3 (ConsolePatchContext)
#               STORE_NAME               3 (ConsolePatchContext)
#               IMPORT_FROM              4 (compile_console_command)
#               STORE_NAME               4 (compile_console_command)
#               POP_TOP
# 
#   7           LOAD_SMALL_INT           1
#               LOAD_CONST               2 (('LoadedUi', 'UiLayoutError', 'build_ui_runtime', 'load_layout_document', 'load_node_meta_dir', 'load_ui'))
#               IMPORT_NAME              5 (loader)
#               IMPORT_FROM              6 (LoadedUi)
#               STORE_NAME               6 (LoadedUi)
#               IMPORT_FROM              7 (UiLayoutError)
#               STORE_NAME               7 (UiLayoutError)
#               IMPORT_FROM              8 (build_ui_runtime)
#               STORE_NAME               8 (build_ui_runtime)
#               IMPORT_FROM              9 (load_layout_document)
#               STORE_NAME               9 (load_layout_document)
#               IMPORT_FROM             10 (load_node_meta_dir)
#               STORE_NAME              10 (load_node_meta_dir)
#               IMPORT_FROM             11 (load_ui)
#               STORE_NAME              11 (load_ui)
#               POP_TOP
# 
#  15           LOAD_SMALL_INT           1
#               LOAD_CONST               3 (('PatchApplyResult', 'apply_patch_ops'))
#               IMPORT_NAME             12 (patch_engine)
#               IMPORT_FROM             13 (PatchApplyResult)
#               STORE_NAME              13 (PatchApplyResult)
#               IMPORT_FROM             14 (apply_patch_ops)
#               STORE_NAME              14 (apply_patch_ops)
#               POP_TOP
# 
#  16           LOAD_SMALL_INT           1
#               LOAD_CONST               4 (('AddNodeOp', 'MoveNodeOp', 'PatchOp', 'RemoveNodeOp', 'RenameNodeOp', 'ResizeNodeOp', 'SetNodeRectOp', 'UpdateNodeMetaOp'))
#               IMPORT_NAME             15 (patch_ops)
#               IMPORT_FROM             16 (AddNodeOp)
#               STORE_NAME              16 (AddNodeOp)
#               IMPORT_FROM             17 (MoveNodeOp)
#               STORE_NAME              17 (MoveNodeOp)
#               IMPORT_FROM             18 (PatchOp)
#               STORE_NAME              18 (PatchOp)
#               IMPORT_FROM             19 (RemoveNodeOp)
#               STORE_NAME              19 (RemoveNodeOp)
#               IMPORT_FROM             20 (RenameNodeOp)
#               STORE_NAME              20 (RenameNodeOp)
#               IMPORT_FROM             21 (ResizeNodeOp)
#               STORE_NAME              21 (ResizeNodeOp)
#               IMPORT_FROM             22 (SetNodeRectOp)
#               STORE_NAME              22 (SetNodeRectOp)
#               IMPORT_FROM             23 (UpdateNodeMetaOp)
#               STORE_NAME              23 (UpdateNodeMetaOp)
#               POP_TOP
# 
#  26           LOAD_SMALL_INT           1
#               LOAD_CONST               5 (('save_layout_document', 'save_node_meta_dir', 'save_ui'))
#               IMPORT_NAME             24 (persistence)
#               IMPORT_FROM             25 (save_layout_document)
#               STORE_NAME              25 (save_layout_document)
#               IMPORT_FROM             26 (save_node_meta_dir)
#               STORE_NAME              26 (save_node_meta_dir)
#               IMPORT_FROM             27 (save_ui)
#               STORE_NAME              27 (save_ui)
#               POP_TOP
# 
#  27           LOAD_SMALL_INT           1
#               LOAD_CONST               6 (('UtfRenderResult', 'render_utf_runtime'))
#               IMPORT_NAME             28 (render)
#               IMPORT_FROM             29 (UtfRenderResult)
#               STORE_NAME              29 (UtfRenderResult)
#               IMPORT_FROM             30 (render_utf_runtime)
#               STORE_NAME              30 (render_utf_runtime)
#               POP_TOP
# 
#  28           LOAD_SMALL_INT           1
#               LOAD_CONST               7 (('LayoutDocument', 'LayoutNode', 'NlpMeta', 'NodeMeta', 'Rect', 'ScreenSpec', 'SnapLink', 'UiNode', 'UiRuntime'))
#               IMPORT_NAME             31 (schema)
#               IMPORT_FROM             32 (LayoutDocument)
#               STORE_NAME              32 (LayoutDocument)
#               IMPORT_FROM             33 (LayoutNode)
#               STORE_NAME              33 (LayoutNode)
#               IMPORT_FROM             34 (NlpMeta)
#               STORE_NAME              34 (NlpMeta)
#               IMPORT_FROM             35 (NodeMeta)
#               STORE_NAME              35 (NodeMeta)
#               IMPORT_FROM             36 (Rect)
#               STORE_NAME              36 (Rect)
#               IMPORT_FROM             37 (ScreenSpec)
#               STORE_NAME              37 (ScreenSpec)
#               IMPORT_FROM             38 (SnapLink)
#               STORE_NAME              38 (SnapLink)
#               IMPORT_FROM             39 (UiNode)
#               STORE_NAME              39 (UiNode)
#               IMPORT_FROM             40 (UiRuntime)
#               STORE_NAME              40 (UiRuntime)
#               POP_TOP
# 
#  40           BUILD_LIST               0
# 
#  41           LOAD_CONST               8 ('ConsoleCommandError')
# 
#  40           LIST_APPEND              1
# 
#  42           LOAD_CONST               9 ('ConsoleCommandResult')
# 
#  40           LIST_APPEND              1
# 
#  43           LOAD_CONST              10 ('ConsolePatchContext')
# 
#  40           LIST_APPEND              1
# 
#  44           LOAD_CONST              11 ('LoadedUi')
# 
#  40           LIST_APPEND              1
# 
#  45           LOAD_CONST              12 ('LayoutDocument')
# 
#  40           LIST_APPEND              1
# 
#  46           LOAD_CONST              13 ('LayoutNode')
# 
#  40           LIST_APPEND              1
# 
#  47           LOAD_CONST              14 ('MoveNodeOp')
# 
#  40           LIST_APPEND              1
# 
#  48           LOAD_CONST              15 ('NlpMeta')
# 
#  40           LIST_APPEND              1
# 
#  49           LOAD_CONST              16 ('NodeMeta')
# 
#  40           LIST_APPEND              1
# 
#  50           LOAD_CONST              17 ('PatchApplyResult')
# 
#  40           LIST_APPEND              1
# 
#  51           LOAD_CONST              18 ('PatchOp')
# 
#  40           LIST_APPEND              1
# 
#  52           LOAD_CONST              19 ('Rect')
# 
#  40           LIST_APPEND              1
# 
#  53           LOAD_CONST              20 ('RemoveNodeOp')
# 
#  40           LIST_APPEND              1
# 
#  54           LOAD_CONST              21 ('RenameNodeOp')
# 
#  40           LIST_APPEND              1
# 
#  55           LOAD_CONST              22 ('ResizeNodeOp')
# 
#  40           LIST_APPEND              1
# 
#  56           LOAD_CONST              23 ('ScreenSpec')
# 
#  40           LIST_APPEND              1
# 
#  57           LOAD_CONST              24 ('SetNodeRectOp')
# 
#  40           LIST_APPEND              1
# 
#  58           LOAD_CONST              25 ('SnapLink')
# 
#  40           LIST_APPEND              1
# 
#  59           LOAD_CONST              26 ('AddNodeOp')
# 
#  40           LIST_APPEND              1
# 
#  60           LOAD_CONST              27 ('compile_console_command')
# 
#  40           LIST_APPEND              1
# 
#  61           LOAD_CONST              28 ('UtfRenderResult')
# 
#  40           LIST_APPEND              1
# 
#  62           LOAD_CONST              29 ('render_utf_runtime')
# 
#  40           LIST_APPEND              1
# 
#  63           LOAD_CONST              30 ('save_layout_document')
# 
#  40           LIST_APPEND              1
# 
#  64           LOAD_CONST              31 ('save_node_meta_dir')
# 
#  40           LIST_APPEND              1
# 
#  65           LOAD_CONST              32 ('save_ui')
# 
#  40           LIST_APPEND              1
# 
#  66           LOAD_CONST              33 ('UiLayoutError')
# 
#  40           LIST_APPEND              1
# 
#  67           LOAD_CONST              34 ('UiNode')
# 
#  40           LIST_APPEND              1
# 
#  68           LOAD_CONST              35 ('UiRuntime')
# 
#  40           LIST_APPEND              1
# 
#  69           LOAD_CONST              36 ('UpdateNodeMetaOp')
# 
#  40           LIST_APPEND              1
# 
#  70           LOAD_CONST              37 ('apply_patch_ops')
# 
#  40           LIST_APPEND              1
# 
#  71           LOAD_CONST              38 ('build_ui_runtime')
# 
#  40           LIST_APPEND              1
# 
#  72           LOAD_CONST              39 ('load_layout_document')
# 
#  40           LIST_APPEND              1
# 
#  73           LOAD_CONST              40 ('load_node_meta_dir')
# 
#  40           LIST_APPEND              1
# 
#  74           LOAD_CONST              41 ('load_ui')
# 
#  40           LIST_APPEND              1
#               STORE_NAME              41 (__all__)
#               LOAD_CONST              42 (None)
#               RETURN_VALUE