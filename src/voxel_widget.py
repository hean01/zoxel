# voxel_widget.py
# A 3D OpenGL QT Widget
# Copyright (c) 2013, Graham R King
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import math
import array
import sys
from PySide import QtCore, QtGui, QtOpenGL
from OpenGL.GL import *
from OpenGL.GLU import gluUnProject, gluProject
import voxel
from euclid import LineSegment3, Plane, Point3, Vector3
from tool import EventData, MouseButtons, KeyModifiers
from voxel_grid import GridPlanes
from voxel_grid import VoxelGrid
import time

class GLWidget(QtOpenGL.QGLWidget):

    # Constants for referring to axis
    X_AXIS = 1
    Y_AXIS = 2
    Z_AXIS = 3
    
    # Drag types
    DRAG_START = 1
    DRAG_END = 2
    DRAG = 3

    @property
    def axis_grids(self):
        return self._display_axis_grids
    @axis_grids.setter
    def axis_grids(self, value):
        self._display_axis_grids = value
        self.updateGL()

    @property
    def wireframe(self):
        return self._display_wireframe
    @wireframe.setter
    def wireframe(self, value):
        self._display_wireframe = value
        self.updateGL()

    @property
    def voxel_colour(self):
        return self._voxel_colour
    @voxel_colour.setter
    def voxel_colour(self, value):
        self._voxel_colour = value

    @property
    def background(self):
        return self._background_colour
    @background.setter
    def background(self, value):
        self._background_colour = value
        self.updateGL()

    @property
    def voxel_edges(self):
        return self._voxeledges
    @voxel_edges.setter
    def voxel_edges(self, value):
        self._voxeledges = value
        self.updateGL()

    @property
    def grids(self):
        return self._grids

    # Our signals
    mouse_click_event = QtCore.Signal()
    start_drag_event = QtCore.Signal()
    drag_event = QtCore.Signal()
    end_drag_event = QtCore.Signal()

    def __init__(self, parent = None):
        glformat = QtOpenGL.QGLFormat()
        glformat.setVersion(1, 1)
        glformat.setProfile(QtOpenGL.QGLFormat.CoreProfile)
        QtOpenGL.QGLWidget.__init__(self, glformat, parent)
        # Test we have a valid context
        ver = QtOpenGL.QGLFormat.openGLVersionFlags()
        if not ver & QtOpenGL.QGLFormat.OpenGL_Version_1_1:
            raise Exception("Requires OpenGL Version 1.1 or above.")
        # Default values
        self._background_colour = QtGui.QColor("silver")
        self._display_wireframe = False
        self._voxel_colour = QtGui.QColor.fromHsvF(0, 1.0, 1.0)
        self._voxeledges = True
        # Mouse position
        self._mouse = QtCore.QPoint()
        self._mouse_absolute = QtCore.QPoint()
        self.mouse_delta_relative = (0,0)
        self.mouse_delta_absolute = (0,0)
        self.mouse_position = (0,0)
        # Default camera
        self.reset_camera(False)
        # zoom
        self._zoom_speed = 0.1
        # Render axis grids?
        self._display_axis_grids = True
        # Our voxel scene
        self.voxels = voxel.VoxelData()
        # Grid manager
        self._grids = VoxelGrid(self.voxels)
        # create the default _grids
        self.grids.add_grid_plane(GridPlanes.X, offset = 0, visible = True,
            color = QtGui.QColor(0x6c, 0x7d, 0x67))
        self.grids.add_grid_plane(GridPlanes.Y, offset = 0, visible = True,
            color = QtGui.QColor(0x65, 0x65, 0x7b))
        self.grids.add_grid_plane(GridPlanes.Z, offset = self.voxels.depth,
            visible = True, color = QtGui.QColor(0x7b, 0x65, 0x68))
        # Used to track the z component of various mouse activity
        self._depth_focus = 1
        # Keep track how long mouse buttons are down for
        self._mousedown_time = 0
        self.button_down = None
        self._dragging = False
        self._key_modifiers = 0

    # Reset the control and clear all data
    def clear(self):
        self.voxels.clear()
        self.refresh()

    # Force an update of our internal data
    def refresh(self):
        self.build_mesh()
        self.build_grids()
        self.updateGL()

    # Reset camera position to defaults
    def reset_camera(self, update = True):
        self._translate_x = 0
        self._translate_y = 0
        self._translate_z = -30
        self._rotate_x = 0
        self._rotate_y = 0
        self._rotate_z = 0
        if update:
            self.updateGL()

    # Initialise OpenGL
    def initializeGL(self):
        # Set background colour
        self.qglClearColor(self._background_colour)
        # Our polygon winding order is clockwise
        glFrontFace(GL_CW)
        # Enable depth testing
        glEnable(GL_DEPTH_TEST)
        # Enable backface culling
        glCullFace(GL_BACK)
        glEnable(GL_CULL_FACE)
        # Shade model
        glShadeModel(GL_SMOOTH)
        # Texture support
        glEnable(GL_TEXTURE_2D)
        # Load our texture
        pixmap = QtGui.QPixmap(":/images/gfx/texture.png")
        self._texture = self.bindTexture(pixmap)
        self.build_mesh()
        # Setup our lighting
        self.setup_lights()

    # Render our scene
    def paintGL(self):
        self.qglClearColor(self._background_colour)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self._translate_x, self._translate_y, self._translate_z)
        glRotated(self._rotate_x, 1.0, 0.0, 0.0)
        glRotated(self._rotate_y, 0.0, 1.0, 0.0)
        glRotated(self._rotate_z, 0.0, 0.0, 1.0)

        # Enable vertex buffers
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)

        # Wireframe?
        if self.wireframe:
            glPolygonMode(GL_FRONT, GL_LINE)

        # Bind our texture
        glBindTexture(GL_TEXTURE_2D, self._texture)

        # Describe our buffers
        glVertexPointer(3, GL_FLOAT, 0, self._vertices)
        if self._voxeledges:
            glTexCoordPointer(2, GL_FLOAT, 0, self._uvs)
        else:
            glDisable(GL_TEXTURE_2D)
        glColorPointer(3, GL_UNSIGNED_BYTE, 0, self._colours)
        glNormalPointer(GL_FLOAT, 0, self._normals)

        # Render the buffers
        glDrawArrays(GL_TRIANGLES, 0, self._num_vertices)

        glDisableClientState(GL_VERTEX_ARRAY)
        glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_NORMAL_ARRAY)

        if not self._voxeledges:
            glEnable(GL_TEXTURE_2D)

        # draw the grids
        if self._display_axis_grids:
            self.grids.paint()

        # Default back to filled rendering
        glPolygonMode(GL_FRONT, GL_FILL)

    # Window is resizing
    def resizeGL(self, width, height):
        self._width = width
        self._height = height
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        self.perspective(45.0, float(width) / height, 0.1, 300)
        glMatrixMode(GL_MODELVIEW)

    # Render scene as colour ID's
    def paintID(self):
        # Disable lighting
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)

        # Render with white background
        self.qglClearColor(QtGui.QColor.fromRgb(0xff, 0xff, 0xff))

        # Ensure we fill our polygons
        glPolygonMode(GL_FRONT, GL_FILL)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self._translate_x, self._translate_y, self._translate_z)
        glRotated(self._rotate_x, 1.0, 0.0, 0.0)
        glRotated(self._rotate_y, 0.0, 1.0, 0.0)
        glRotated(self._rotate_z, 0.0, 0.0, 1.0)

        # Enable vertex buffers
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)

        # Describe our buffers
        glVertexPointer(3, GL_FLOAT, 0, self._vertices)
        glColorPointer(3, GL_UNSIGNED_BYTE, 0, self._colour_ids)
        glNormalPointer(GL_FLOAT, 0, self._normals)

        # Render the buffers
        glDrawArrays(GL_TRIANGLES, 0, self._num_vertices)

        glDisableClientState(GL_VERTEX_ARRAY)
        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_NORMAL_ARRAY)

        # Set background colour back to original
        self.qglClearColor(self._background_colour)

        # Re-enable lighting
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)

    def perspective(self, fovY, aspect, zNear, zFar):
        fH = math.tan(fovY / 360.0 * math.pi) * zNear
        fW = fH * aspect
        glFrustum(-fW, fW, -fH, fH, zNear, zFar)

    def setup_lights(self):
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)

    # Build a mesh from our current voxel data
    def build_mesh(self):
        # Grab the voxel vertices
        (self._vertices, self._colours, self._normals,
         self._colour_ids, self._uvs) = self.voxels.get_vertices()
        self._num_vertices = len(self._vertices) // 3
        self._vertices = array.array("f", self._vertices).tostring()
        self._colours = array.array("B", self._colours).tostring()
        self._colour_ids = array.array("B", self._colour_ids).tostring()
        self._normals = array.array("f", self._normals).tostring()
        self._uvs = array.array("f", self._uvs).tostring()

    # Build axis grids
    def build_grids(self):
        self.grids.update_grid_plane(self.voxels)

    def mousePressEvent(self, event):
        
        self._key_modifiers = event.modifiers()
        self._mousedown_time = time.time()
        
        self._mouse = QtCore.QPoint(event.pos())
        self._mouse_absolute = QtCore.QPoint(event.pos())
        self.mouse_position = (self._mouse.x(),self._mouse.y())

        self._button_down = None
        if event.buttons() & QtCore.Qt.LeftButton:
            self._button_down = MouseButtons.LEFT
        elif event.buttons() & QtCore.Qt.MiddleButton:
            self._button_down = MouseButtons.MIDDLE
        elif event.buttons() & QtCore.Qt.RightButton:
            self._button_down = MouseButtons.RIGHT

        # Remember the 3d coordinates of this click
        mx, my, mz, d = self.window_to_world(event.x(), event.y())
        mxd, myd, mzd, _ = self.window_to_world(event.x() + 1, event.y(), d)
        self._htranslate = ((mxd - mx), (myd - my), (mzd - mz))
        mxd, myd, mzd, _ = self.window_to_world(event.x(), event.y() + 1, d)
        self._vtranslate = ((mxd - mx), (myd - my), (mzd - mz))
        # Work out translation for x,y
        ax, ay = self.view_axis()
        if ax == self.X_AXIS:
            self._htranslate = abs(self._htranslate[0])
        if ax == self.Y_AXIS:
            self._htranslate = abs(self._htranslate[1])
        if ax == self.Z_AXIS:
            self._htranslate = abs(self._htranslate[2])
        if ay == self.X_AXIS:
            self._vtranslate = abs(self._vtranslate[0])
        if ay == self.Y_AXIS:
            self._vtranslate = abs(self._vtranslate[1])
        if ay == self.Z_AXIS:
            self._vtranslate = abs(self._vtranslate[2])
        self._depth_focus = d

    def mouseMoveEvent(self, event):

        self.mouse_position = (self._mouse.x(),self._mouse.y())

        ctrl = (self._key_modifiers 
                & QtCore.Qt.KeyboardModifier.ControlModifier) != 0
        shift = (self._key_modifiers 
                 & QtCore.Qt.KeyboardModifier.ShiftModifier) != 0

        # Screen units delta
        dx = event.x() - self._mouse.x()
        dy = event.y() - self._mouse.y()
        
        # Remember the mouse deltas
        self.mouse_delta_relative = (dx, dy)
        self.mouse_delta_absolute = (event.x() - self._mouse_absolute.x(), 
            event.y() - self._mouse_absolute.y())

        # Check if we should propagate mouse event or just consume for
        # internal actions; rotate, translate
        consumeEvent = False
        if event.buttons() & QtCore.Qt.MiddleButton or (event.buttons() & QtCore.Qt.RightButton and ctrl):
            consumeEvent = True

        # Maybe we are dragging
        if time.time() - self._mousedown_time > 0.3 and not self._dragging:
            self._dragging = True
            if not consumeEvent:
                # Announce the start of a drag
                x, y, z, face = self.window_to_voxel(event.x(), event.y())
                self.send_drag(self.DRAG_START, x, y, z, event.x(), event.y(), face)
                self.refresh()
        elif time.time() - self._mousedown_time > 0.3 and self._dragging:
            if not consumeEvent:
                # Already dragging - send a drag event
                x, y, z, face = self.window_to_voxel(event.x(), event.y())
                self.send_drag(self.DRAG, x, y, z, event.x(), event.y(), face)
                self.refresh()

        # Right mouse button held down with CTRL key - rotate
        # Or middle mouse button held 
        if ((event.buttons() & QtCore.Qt.RightButton and ctrl)
            or ((event.buttons() & QtCore.Qt.MiddleButton) and not ctrl)):
            self._rotate_x = self._rotate_x + dy
            self._rotate_y = self._rotate_y + dx
            self.updateGL()

        # Middle mouse button held down with CTRL - translate
        if event.buttons() & QtCore.Qt.MiddleButton and ctrl:
            
            # Work out the translation in 3d space
            self._translate_x = self._translate_x + dx * self._htranslate
            self._translate_y = self._translate_y + ((-dy) * self._vtranslate)
            self.refresh()

        self._mouse = QtCore.QPoint(event.pos())

    def mouseReleaseEvent(self, event):
        self._mouse = QtCore.QPoint(event.pos())
        x, y, z, face = self.window_to_voxel(event.x(), event.y())
        # Send event depenand if this is a click or a drag
        if self._dragging:
            self._dragging = False
            self.send_drag(self.DRAG_END, x, y, z, event.x(), event.y(), face)
        else:
            self.send_mouse_click(x, y, z, event.x(), event.y(), face)
        self.refresh()

    def zoom_in(self):
        self._translate_z *= 1 - self._zoom_speed
        self.updateGL()
        
    def zoom_out(self):
        self._translate_z *= 1 + self._zoom_speed        
        self.updateGL()

    def wheelEvent(self, event):
        if event.delta() > 0:
            self._translate_z *= 1 + self._zoom_speed
        else:
            self._translate_z *= 1 - self._zoom_speed
        self.updateGL()

    # Return voxel space x,y,z coordinates given x, y window coordinates
    # Also return an identifier which indicates which face was clicked on.
    # If the background was clicked on rather than a voxel, calculate and return
    # the location on the floor grid.
    def window_to_voxel(self, x, y):
        # We must invert y coordinates
        y = self._height - y
        # Render our scene (to the back buffer) using colour IDs
        self.paintID()
        # Grab the colour / ID at the coordinates
        c = glReadPixels(x, y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
        if type(c) is str:
            # This is what MESA on Linux seems to return
            # Grab the colour (ID) which was clicked on
            voxelid = ord(c[0]) << 16 | ord(c[1]) << 8 | ord(c[2])
        else:
            # Windows seems to return an array
            voxelid = c[0][0][0] << 16 | c[1][0][0] << 8 | c[2][0][0]

        # Perhaps we clicked on the background?
        if voxelid == 0xffffff:
            x, y, z = self.plane_intersection(x, y)
            if x is None:
                return None, None, None, None
            return x, y, z, None
        # Decode the colour ID into x,y,z,face
        x = (voxelid & 0xfe0000) >> 17
        y = (voxelid & 0x1fc00) >> 10
        z = (voxelid & 0x3f8) >> 3
        face = voxelid & 0x07
        # Return what we learned
        return x, y, z, face

    # Calculate the intersection between mouse coordinates and a plane
    def plane_intersection(self, x, y):
        # Unproject coordinates into object space
        nx, ny, nz = gluUnProject(x, y, 0.0)
        fx, fy, fz = gluUnProject(x, y, 1.0)
        # Calculate the ray
        near = Point3(nx, ny, nz)
        far = Point3(fx, fy, fz)
        ray = LineSegment3(near, far)
        # Define our planes
        # XXX origin assumes planes are at zero offsets, should really
        # XXX respect any grid plane offset here
        origin = self.voxels.voxel_to_world(0, 0, self.voxels.depth)
        planes = (
            Plane(Vector3(1, 0, 0), origin[0]),
            Plane(Vector3(0, 1, 0), origin[1]),
            Plane(Vector3(0, 0, 1), origin[2]+0.001))
        intersection = None, None, None
        distance = sys.maxint
        for plane in planes:
            # Get intersection point
            intersect = plane.intersect(ray)
            if intersect:
                # Adjust to voxel space coordinates
                x, y, z = self.voxels.world_to_voxel(intersect.x,
                    intersect.y, intersect.z)
                x = int(x)
                y = int(y)
                z = int(z)
                # Ignore out of bounds insections
                if not self.voxels.is_valid_bounds(x, y, z):
                    continue
                length = near.distance(Point3(intersect.x, intersect.y, intersect.z))
                if length < distance:
                    intersection = int(x), int(y), int(z)
                    distance = length
        return intersection

    # Determine the axis which are perpendicular to our viewing ray, ish
    def view_axis(self):
        # Shoot a ray into the scene
        x1, y1, z1 = gluUnProject(self.width() // 2, self.height() // 2, 0.0)
        x2, y2, z2 = gluUnProject(self.width() // 2, self.height() // 2, 1.0)
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        dz = abs(z2 - z1)
        # The largest deviation is the axis we're looking down
        if dz >= dx and dz >= dy:
            return (self.X_AXIS, self.Y_AXIS)
        elif dy >= dx and dy >= dz:
            return (self.X_AXIS, self.Z_AXIS)
        return (self.Z_AXIS, self.Y_AXIS)

    # Convert window x,y coordinates into x,y,z world coordinates, also return
    # the depth
    def window_to_world(self, x, y, z = None):
        # Find depth
        y = self._height - y
        if z is None:
            z = glReadPixels(x, y, 1, 1, GL_DEPTH_COMPONENT, GL_FLOAT)[0][0]
        fx, fy, fz = gluUnProject(x, y, z)
        return fx, fy, fz, z

    # Convert x,y,z world coorindates to x,y window coordinates
    def world_to_window(self, x, y, z):
        x, y, z = gluProject(x, y, z)
        y = self._height - y
        return x, y

    def _build_event(self, x, y, z, mouse_x, mouse_y, face):
        data = EventData()
        data.world_x = x
        data.world_y = y
        data.world_z = z
        data.face = face
        data.mouse_x = mouse_x
        data.mouse_y = mouse_y
        data.mouse_button = self._button_down
        data.key_modifiers = self._key_modifiers
        data.voxels = self.voxels
        return data

    def send_mouse_click(self, x, y, z, mouse_x, mouse_y, face):
        self.target = self._build_event(x, y, z, mouse_x, mouse_y, face)
        self.mouse_click_event.emit()

    def send_drag(self, dragtype, x, y, z, mouse_x, mouse_y, face):
        self.target = self._build_event(x, y, z, mouse_x, mouse_y, face)
        if dragtype == self.DRAG_START:
            self.start_drag_event.emit()
        elif dragtype == self.DRAG_END:
            self.end_drag_event.emit()
        elif dragtype == self.DRAG:
            self.drag_event.emit()
