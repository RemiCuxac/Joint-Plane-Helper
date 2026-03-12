import maya.cmds as cmds

try:
    from PySide2 import QtWidgets, QtCore
except ModuleNotFoundError:
    from PySide6 import QtWidgets, QtCore


def create_normal_shader(*planes: str):
    for obj in planes:
        # create shadingEngine
        shader_name = "proxy_plane_shader"
        shader = cmds.ls(shader_name, type="shadingEngine")
        if not shader:
            shader = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader_name)
        if isinstance(shader, list):
            shader = shader[0]

        # create bump3d
        bump_name = "proxy_plane_bump3d"
        bump = cmds.ls(bump_name, type="bump3d")
        if not bump:
            bump = cmds.shadingNode("bump3d", asUtility=True, asShader=True, name=bump_name)
        if isinstance(bump, list):
            bump = bump[0]

        # connect bump3d to shader
        src = bump + ".outNormal"
        dst = shader + ".surfaceShader"
        shaderConnections = cmds.listConnections(dst, source=True, destination=False)
        if not shaderConnections or bump not in shaderConnections:
            cmds.connectAttr(src, dst, force=True)

        # connect shader to obj
        cmds.sets(obj, edit=True, forceElement=shader)


def build_proxy_planes(joints, size=1, up_axis=1):
    if not joints:
        cmds.warning("Select at least one joint.")
        return
    planes = []
    nodes = []
    jntSizeFactor = cmds.jointDisplayScale(q=True)
    multiplier = size
    axis = {0: [1, 0, 0], 1: [0, 1, 0], 2: [0, 0, 1]}[up_axis]
    length = None
    for i, jnt in enumerate(joints):
        plane_name = f"proxy_plane_{jnt.split('|')[-1]}"
        plane, planeParams = cmds.nurbsPlane(u=1, v=1, axis=axis, d=1, ch=True, name=plane_name)
        multNode = cmds.createNode("multiplyDivide")
        cmds.setAttr(f"{multNode}.input2X", 0.5)
        jntSize = cmds.getAttr(f"{jnt}.radius")
        cmds.connectAttr(f"{planeParams}.width", f"{multNode}.input1X")
        cmds.connectAttr(f"{multNode}.outputX", f"{planeParams}.pivotX")
        ratio = jntSizeFactor * jntSize * multiplier
        # set length and width
        if len(joints) > i + 1:
            cmds.connectAttr(f"{joints[i + 1]}.translateX", f"{planeParams}.width")
            length = cmds.getAttr(f"{joints[i + 1]}.translateX")
            cmds.setAttr(f"{planeParams}.lengthRatio", ratio / length)
        else:
            cmds.setAttr(f"{planeParams}.width", length or (5 * ratio) / jntSizeFactor)
            cmds.setAttr(f"{planeParams}.lengthRatio", ratio / length if length else multiplier * 0.2 * jntSizeFactor)
        cmds.matchTransform(plane, jnt)
        create_normal_shader(plane)
        cmds.setAttr(f"{plane}.overrideEnabled", True)
        cmds.setAttr(f"{plane}.overrideDisplayType", 2)
        newPlane = cmds.parent(plane, jnt)[0]
        planes.append(newPlane)
        nodes.append(multNode)
        nodes.append(planeParams)

    # add to a new objectSet for easier selection
    proxySet = cmds.ls("proxyPlaneSet", type="objectSet")
    if not proxySet:
        proxySet = cmds.sets(name="proxyPlaneSet")
    proxySet = proxySet[0] if isinstance(proxySet, list) else proxySet
    cmds.sets(planes, add=proxySet)
    cmds.sets(nodes, add=proxySet)
    bump_node = cmds.ls("proxy_plane_bump3d", type="bump3d")
    if bump_node:
        cmds.sets(bump_node, add=proxySet)
    cmds.select(planes)
    cmds.inViewMessage(amg=f'<hl>Created {len(planes)} proxy planes</hl>', pos='midCenter', fade=True)
    return planes


class ProxyPlaneWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Create Proxy Planes")
        self.setMinimumWidth(300)
        self.last_slider_val = 1
        self.planes_created = False
        self.selection = []
        self._create_layout()
        self._connect_signals()
        self._store_selection()
        self.show()

    def _store_selection(self):
        self.selection = cmds.ls(selection=True, type="joint")
        if not self.selection:
            proxyPlanes = []
            for obj in cmds.ls(selection=True, type="transform"):
                for shape in cmds.listRelatives(obj, shapes=True):
                    if cmds.objectType(shape) == "nurbsSurface":
                        proxyPlanes.append(obj)
            if proxyPlanes:
                cmds.select(proxyPlanes)
                self.planes_created = True
            return

    def _create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()
        self.qcb_axis = QtWidgets.QComboBox()
        self.qcb_axis.addItems(['x', 'y', 'z'])
        self.qcb_axis.setCurrentText('y')
        size_container = QtWidgets.QHBoxLayout()
        self.qsl_size = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.qsl_size.setMinimum(-100)
        self.qsl_size.setMaximum(100)
        self.qsl_size.setValue(self.last_slider_val)
        size_container.addWidget(self.qsl_size)
        self.qpb_create = QtWidgets.QPushButton("Create Proxy Planes")
        form_layout.addRow("Up Axis:", self.qcb_axis)
        form_layout.addRow("Size:", size_container)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.qpb_create)

    def _connect_signals(self):
        self.qpb_create.clicked.connect(self.create_planes)
        self.qsl_size.valueChanged.connect(self._handle_slider_drag)
        self.qsl_size.sliderReleased.connect(self._reset_slider)

    def _handle_slider_drag(self, current_val):
        if not self.planes_created or current_val == self.last_slider_val:
            return
        is_increasing = current_val > self.last_slider_val
        self.last_slider_val = current_val
        up_axis_idx = self.qcb_axis.currentIndex()
        scale_attr = "scaleY" if up_axis_idx == 2 else "scaleZ"
        sel = cmds.ls(selection=True)
        if sel:
            scale_factor = 1.05 if is_increasing else 0.95
            for obj in sel:
                if "proxy_plane" in obj:
                    val = cmds.getAttr(f"{obj}.{scale_attr}")
                    cmds.setAttr(f"{obj}.{scale_attr}", val * scale_factor)

    def _reset_slider(self):
        self.qsl_size.blockSignals(True)
        self.qsl_size.setValue(1)
        self.qsl_size.blockSignals(False)
        self.last_slider_val = 1

    def create_planes(self):
        cmds.undoInfo(chunkName="before proxy planes", openChunk=True)
        if not self.selection:
            cmds.warning("Select at least one joint.")
            return
        up_axis = self.qcb_axis.currentIndex()
        size = self.qsl_size.value()
        build_proxy_planes(self.selection, size, up_axis=up_axis)
        # Enable slider scaling logic now that planes exist
        self.planes_created = True
        cmds.undoInfo(closeChunk=True)


tool = ProxyPlaneWindow()
