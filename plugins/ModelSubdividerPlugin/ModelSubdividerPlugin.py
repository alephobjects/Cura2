# Copyright (c) 2017 Aleph Objects, Inc.
# Cura is released under the terms of the AGPLv3 or higher.

from UM.Application import Application
from UM.Extension import Extension
from UM.Scene.Plane import Plane
from UM.i18n import i18nCatalog
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Scene.Selection import Selection
from UM.Logger import Logger
from UM.Scene.SceneNode import SceneNode
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from UM.Mesh.MeshBuilder import MeshBuilder
import numpy
import math

i18n_catalog = i18nCatalog("ModelSubdividerPlugin")


class IntersectionType:
    Point = 0
    Segment = 1
    Face = 2


class ModelSubdividerPlugin(Extension):
    epsilon = 1e-2

    def __init__(self):
        super().__init__()
        self.addMenuItem(i18n_catalog.i18n("Create plane"), self.createPlane)
        self.addMenuItem(i18n_catalog.i18n("Subdivide mesh by plane"), self.subdivide)

    def createPlane(self):
        plane = Plane()
        scene = Application.getInstance().getController().getScene()
        operation = AddSceneNodeOperation(plane, scene.getRoot())
        operation.push()

    def subdivide(self):
        if Selection.getCount() != 2:
            Logger.log("w", i18n_catalog.i18n("Cannot subdivide: objects != 2"))
            return
        object1 = Selection.getSelectedObject(0)
        object2 = Selection.getSelectedObject(1)
        if type(object1) is SceneNode and type(object2) is Plane:
            obj = object1
            plane = object2
        elif type(object2) is SceneNode and type(object1) is Plane:
            obj = object2
            plane = object1
        else:
            Logger.log("w", i18n_catalog.i18n("Cannot subdivide: object and plane need to be selected"))
            return

        result = self._subdivide(obj, plane)
        if type(result) is tuple:
            operation = GroupedOperation()
            operation.addOperation(RemoveSceneNodeOperation(plane))
            operation.addOperation(RemoveSceneNodeOperation(obj))
            operation.addOperation(AddSceneNodeOperation(result[0], obj.getParent()))
            if len(result) == 2:
                operation.addOperation(AddSceneNodeOperation(result[1], obj.getParent()))
            operation.push()
        else:
            Logger.log("w", i18n_catalog.i18n("Cannot subdivide"))

    def _subdivide(self, mesh, plane):
        plane_mesh_data = plane.getMeshData()
        plane_vertices = plane_mesh_data.getVertices()
        plane_face = [plane_vertices[0], plane_vertices[1], plane_vertices[2]]
        builders = [MeshBuilder(), MeshBuilder()]
        mesh_data = mesh.getMeshData()
        vertices = mesh_data.getVertices()
        indices = mesh_data.getIndices()
        faces = []
        if indices:
            for index_array in indices:
                faces.append([vertices[index_array[0]], vertices[index_array[1]], vertices[index_array[2]]])
        else:
            for i in range(0, len(vertices), 3):
                faces.append([vertices[i], vertices[i+1], vertices[i+2]])
        intersected_faces = []
        for f in faces:
            intersection_type = self.check_intersection_with_triangle(plane_face, f)
            if intersection_type is None:
                side = self.check_plane_side(plane_face, f)
                self.add_face_to_builder(builders[side], f)
            elif intersection_type is not None and intersection_type[0] == IntersectionType.Point:
                side = self.check_plane_side(plane_face, f)
                self.add_face_to_builder(builders[side], f)
            else:
                intersected_faces.append([f, intersection_type])
        for f in intersected_faces:
            if f[1][0] == IntersectionType.Face:
                self.add_face_to_builder(builders[0], f[0])
                self.add_face_to_builder(builders[1], f[0])
            elif f[1][0] == IntersectionType.Segment:
                new_faces = self.split_triangle(f[0], f[1][1])
                for new_face in new_faces:
                    self.add_face_to_builder(builders[self.check_plane_side(plane_face, new_face)], new_face)
        nodes = [SceneNode(), SceneNode()]
        for n in range(len(nodes)):
            builders[n].calculateNormals()
            nodes[n].setMeshData(builders[n].build())
            nodes[n].setSelectable(True)
            nodes[n].setScale(mesh.getScale())
        return nodes[0], nodes[1]

    def split_triangle(self, face, intersection):
        intersection_points = [intersection[0][0], intersection[1][0]]
        intersection_indices = [intersection[0][1], intersection[1][1]]
        new_faces = []
        common_index = 0
        for i in intersection_indices[0]:
            for i2 in intersection_indices[1]:
                if i == i2:
                    common_index = i
        new_faces.append([face[common_index], intersection_points[0], intersection_points[1]])
        other_index = common_index + 1 if common_index < 2 else 0
        new_faces.append([face[other_index], intersection_points[0], intersection_points[1]])
        third_index = other_index + 1 if other_index < 2 else 0
        third_point = None
        for i in range(len(intersection_indices)):
            if intersection_indices[i][0] == common_index and intersection_indices[i][1] == third_index or \
                    intersection_indices[i][1] == common_index and intersection_indices[i][0] == third_index:
                third_point = intersection_points[i]
                break
        new_faces.append([face[other_index], face[third_index], third_point])
        return new_faces

    def add_face_to_builder(self, builder, face):
        builder.addFaceByPoints(face[0][0], face[0][1], face[0][2],
                                face[1][0], face[1][1], face[1][2],
                                face[2][0], face[2][1], face[2][2])

    def check_plane_side(self, plane_face, face):
        n = numpy.cross(plane_face[1] - plane_face[0], plane_face[2] - plane_face[0])
        v = [plane_face[0] - face[0], plane_face[0] - face[1], plane_face[0] - face[2]]
        d = [numpy.inner(n, v[0]), numpy.inner(n, v[1]), numpy.inner(n, v[2])]
        num_greater = 0
        for k in d:
            if k > self.epsilon:
                num_greater += 1
        if num_greater > 1:
            return 0
        else:
            return 1

    def distance_between_points(self, point1, point2):
        return math.sqrt((point1[0]-point2[0])**2+(point1[1]-point2[1])**2+(point1[2]-point2[2])**2)

    def is_point_in_plane(self, plane_face, point):
        n = numpy.cross(plane_face[1] - plane_face[0], plane_face[2] - plane_face[0])
        v = plane_face[0] - point
        d = numpy.inner(n, v)
        if math.fabs(d) <= self.epsilon:
            return True
        return False

    def check_intersection_with_triangle(self, plane_face, face):
        intersection_points = []
        for i in range(3):
            i2 = i + 1 if i < 2 else 0
            segment = [face[i], face[i2]]
            point = self.check_intersection_with_segment(plane_face, segment)
            if point is not None:
                intersection_points.append([point, [i, i2]])
        if len(intersection_points) == 1:
            return IntersectionType.Point, intersection_points[0][0]
        elif len(intersection_points) == 2:
            if self.distance_between_points(intersection_points[0][0], intersection_points[1][0]) < self.epsilon:
                return IntersectionType.Point, intersection_points[0][0]
            return IntersectionType.Segment, intersection_points
        elif len(intersection_points) == 3:
            return IntersectionType.Face, face
        return None

    def check_intersection_with_segment(self, plane_face, segment):
        n = numpy.cross(plane_face[1] - plane_face[0], plane_face[2] - plane_face[0])
        v = plane_face[0] - segment[0]
        d = numpy.inner(n, v)
        w = segment[1] - segment[0]
        e = numpy.inner(n, w)
        if math.fabs(e) > self.epsilon:
            o = segment[0] + w * d / e
            if numpy.inner(segment[0] - o, segment[1] - o) <= 0:
                return o
        return None
