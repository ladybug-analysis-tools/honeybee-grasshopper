"""Collection of methods for Honeybee geometry operations in Grasshopper."""
import config
from collections import namedtuple

def extractSurfacePoints(HBSurface, *args, **kwargs):
    """Calculate list of points for a HBSurface.

    Args:
        HBSurface: A HBSurface
        --- Grasshopper ---
        triangulate: If set to True the function returns the points for triangulated
            surfaces (Default: False)
        meshingParameters: Optional Rhino meshingParameters. This will only be used
            if the surrface is non-planar or has an internal edge and needs to be meshed.
            Default:
                Rhino.Geometry.MeshingParameters.Coarse; SimplePlanes = True for planar surfaces
                Rhino.Geometry.MeshingParameters.Smooth for non-planar surfaces
        --- Dynamo ---
            maxTessellationDivisions: Maximum number of divisions for surface tessellation.
    Returns:
        A list of point lists. For planar surfaces the length of the list will be
        only 1. For non-planar surfaces or surfaces with internal edges it will be
        a number of lists.
    """
    assert hasattr(HBSurface, 'isHBObject'), "Surface input is not a HBSurface."

    if config.platform.isGrasshopper:
        return __extractSurfacePointsGH(HBSurface.geometry, *args, **kwargs)
    elif config.platform.isRevitOrDynamo:
        return __extractSurfacePointsDS(HBSurface.geometry, *args, **kwargs)

def extractSurfacePointsFromGeometry(geometry, *args, **kwargs):
    """Calculate list of points for a geometry.

    Args:
        geometry: A Grasshopper or Dynamo geometry
        --- Grasshopper ---
        triangulate: If set to True the function returns the points for triangulated
            surfaces (Default: False)
        meshingParameters: Optional Rhino meshingParameters. This will only be used
            if the surrface is non-planar or has an internal edge and needs to be meshed.
            Default:
                Rhino.Geometry.MeshingParameters.Coarse; SimplePlanes = True for planar surfaces
                Rhino.Geometry.MeshingParameters.Smooth for non-planar surfaces
        --- Dynamo ---
            maxTessellationDivisions: Maximum number of divisions for surface tessellation.
    Returns:
        A list of point lists. For planar surfaces the length of the list will be
        only 1. For non-planar surfaces or surfaces with internal edges it will be
        a number of lists.
    """
    try:
        if config.platform.isGrasshopper:
            return __extractSurfacePointsGH(geometry, *args, **kwargs)
        elif config.platform.isRevitOrDynamo:
            return __extractSurfacePointsDS(geometry, *args, **kwargs)
    except Exception as e:
        raise ValueError("Failed to extract points!\n%s" % e)

# TODO: Add support for non-planar surfaces. The current implementation is a simple
# implementation to prototype the workflow
# TODO: Extract point should support mesh as well as brep surfaces. Currently we have
# two alternative solutions which is not preferred. Currently it only works for Breps.
def __extractSurfacePointsGH(geometry, triangulate=False, meshingParameters=None):
    """Calculate list of points for a HBSurface.

    For planar surfaces the length of the list will be only 1. For non-planar
    surfaces or surfaces with internal edges it will be a number of lists.

    Args:
        geometry: A Mesh or Brep
        triangulate: If set to True the function returns the points for triangulated
            surfaces (Default: False)
        meshingParameters: Optional Rhino meshingParameters. This will only be used if the
            surface is non-planar or has an internal edge and needs to be meshed.
            Default:
                Rhino.Geometry.MeshingParameters.Coarse; SimplePlanes = True for planar surfaces
                Rhino.Geometry.MeshingParameters.Smooth for non-planar surfaces
    Returns:
        A list of point lists. For planar surfaces the length of the list will be
        only 1. For non-planar surfaces or surfaces with internal edges it will be
        a number of lists.
    """
    assert isinstance(geometry, config.libs.Rhino.Geometry.GeometryBase), \
        "Input surface should be a Mesh or a Brep."

    assert not isinstance(geometry, config.libs.Rhino.Geometry.Mesh), \
        "Extracting points for mesh surfaces hasn't been implemented."

    pts = geometry.DuplicateVertices()
    # sort points anti clockwise
    # this is only important for energy simulation and won't make a difference
    # for Radiance

    # To sort the points we find border of the surface and evaluate points
    # on border and use the parameter value to sort them
    border = config.libs.Rhino.Geometry.Curve.JoinCurves(
        geometry.DuplicateEdgeCurves(True))[0]

    pointsSorted = sorted(pts, key=lambda pt: border.ClosestPoint(pt)[1])


    # make sure points are anti clockwise
    if not isPointsSortedAntiClockwise(pointsSorted,
                                       getSurfaceCenterPtandNormal(geometry).normalVector):
        return pointsSorted.reverse()

    # return sorted points
    # Wrap in a list as Honeybee accepts list of list of points
    return [pointsSorted]


def __extractSurfacePointsDS(geometry, maxTessellationDivisions=25,
                             joinCoplanarTriFaces=True):
    """Extract points from a surface in Dynamo.

    Args:
        geometry: A Dynamo geometry.
        maxTessellationDivisions: Maximum number of divisions for surface tessellation.
        joinCoplanarTriFaces: Join two triangle faces if there is only two.

    Returns:
        A list of point lists.
    """
    def splitList(li, step=3):
        return [li[x:x + step] for x in range(0, len(li), step)]

    def __getPoints(rp):
        pts = list(rp.MeshVertices)
        # split values in xyz
        xyz = splitList(splitList(pts))
        del(pts)
        return xyz

    rpFactory = config.libs.Dynamo.Visualization.DefaultRenderPackageFactory()
    tp = config.libs.DesignScript.Interfaces.TessellationParameters()
    tp.MaxTessellationDivisions = maxTessellationDivisions
    tp.Tolerance = -1
    rp = rpFactory.CreateRenderPackage()
    geometry.Tessellate(rp, tp)
    pts = __getPoints(rp)

    # check if two faces are generated for this geometry and merge them
    if joinCoplanarTriFaces and len(pts) == 2:
        pts[0].insert(2, pts[1][2])
        pts = [pts[0]]
    # clean Dynamo objects
    del(rpFactory)
    del(rp)
    del(tp)

    return pts


def vectorsCrossProduct(vector1, vector2):
    """Calculate cross product of two vectors."""
    return vector1.X * vector2.X + \
        vector1.Y * vector2.Y + vector1.Z * vector2.Z


def isPointsSortedAntiClockwise(sortedPoints, normal):
    """Check if an ordered list of points are anti-clockwise."""
    if not config.platform:
        raise Exception("This function can only be called from inside Grasshopper " +
                        "or Dynamo")

    if config.platform == "gh":
        vector0 = config.libs.Rhino.Geometry.Vector3d(sortedPoints[1] - sortedPoints[0])
        vector1 = config.libs.Rhino.Geometry.Vector3d(sortedPoints[-1] - sortedPoints[0])
        ptsNormal = config.libs.Rhino.Geometry.Vector3d.CrossProduct(vector0, vector1)

    elif config.platform == "ds" or config.platform == "rvt":
        vector0 = config.libs.DesignScript.Geometry.Vector.ByTwoPoints(sortedPoints[0], sortedPoints[1])
        vector1 = config.libs.DesignScript.Geometry.Vector.ByTwoPoints(sortedPoints[0], sortedPoints[-1])
        ptsNormal = config.libs.DesignScript.Geometry.Vector.Cross(vector0, vector1)

    # in case points are anti-clockwise then normals should be parallel
    if vectorsCrossProduct(ptsNormal, normal) > 0:
        return True
    else:
        return False


def getSurfaceCenterPtandNormal(HBSurface):
    """Calculate center point and normal for a HBSurface.

    Args:
        HBSurface: A Honeybee surface

    Returns:
        Returns a tuple as (centerPt, normalVector)
    """
    try:
        geometry = HBSurface.geometry
    except AttributeError as e:
        raise TypeError("Input is not a HBSurface: %s" % str(e))

    if config.platform == 'gh':
        brepFace = geometry.Faces[0]
        if brepFace.IsPlanar and brepFace.IsSurface:
            u_domain = brepFace.Domain(0)
            v_domain = brepFace.Domain(1)
            centerU = (u_domain.Min + u_domain.Max) / 2
            centerV = (v_domain.Min + v_domain.Max) / 2

            centerPt = brepFace.PointAt(centerU, centerV)
            normalVector = brepFace.NormalAt(centerU, centerV)
        else:
            centroid = config.libs.Rhino.Geometry.AreaMassProperties \
                       .Compute(brepFace).Centroid
            uv = brepFace.ClosestPoint(centroid)
            centerPt = brepFace.PointAt(uv[1], uv[2])
            normalVector = brepFace.NormalAt(uv[1], uv[2])

    elif config.platform == "ds" or config.platform == "rvt":
        uv = config.libs.DesignScript.Geometry.UV.ByCoordinates(0.5, 0.5)
        centerPt = geometry.PointAtParameter(uv.U, uv.V)
        normalVector = geometry.NormalAtParameter(uv.U, uv.V).Normalized()

    SurfaceData = namedtuple('SurfaceData', 'centerPt normalVector')

    return SurfaceData(centerPt, normalVector)


def checkPlanarity(HBSurface, tolerance=1e-3):
    """Check planarity of a HBSurface.

    Args:
        HBSurface: A Honeybee surface
        tolerance: A float number as tolerance (Default: 1e-3)

    Returns:
        True is the surface is planar, otherwise return False.
    """
    assert config.platform == 'gh', "This function only works within Grasshopper."

    try:
        return HBSurface.geometry.Faces[0].IsPlanar(tolerance)
    except AttributeError as e:
        raise TypeError("Input is not a HBSurface: %s" % str(e))


def checkForInternalEdge(HBSurface):
    """Check if the surface has an internal edge.

    For surfaces with internal edge surfaces needs to be meshed to extract the points.

    Args:
        HBSurface: A Honeybee surface

    Returns:
        True is the surface has an internal edge, otherwise return False.

    """
    assert config.platform == 'gh', "This function only works within Grasshopper."

    # I believe there should be a direct method in RhinoCommon to indicate if a
    # surface is an open brep but since I couldn't find it I'm using this method
    # if Surface has no intenal edges the length of joined border is 1
    try:
        edges = HBSurface.geometry.DuplicateEdgeCurves(True)
    except AttributeError as e:
        raise TypeError("Input is not a HBSurface: %s" % str(e))
    else:
        border = config.libs.Rhino.Geometry.Curve.JoinCurves(edges)
        if len(border) > 1:
            return True
        else:
            return False


def xyzToGeometricalPoints(xyzPoints):
    """conver a sequence of (x, y, z) values to Dynamo or Grasshopper points."""
    for xyzList in xyzPoints:
        for xyz in xyzList:
            if config.platform.isRevitOrDynamo:
                yield config.platform.libs.DesignScript.Geometry \
                    .Point.ByCoordinates(xyz[0], xyz[1], xyz[2])
            elif config.platform.isGrasshopper:
                yield config.platform.libs.Rhino.Geometry.Point3d(xyz[0],
                                                                  xyz[1],
                                                                  xyz[2])

def polygon(pointList):
    if config.platform.isRevitOrDynamo:
        return config.platform.libs.DesignScript.Geometry \
            .Polygon.ByPoints(pointList)
    elif config.platform.isGrasshopper:
        return config.platform.libs.Rhino.Geometry \
            .Polyline(pointList).ToNurbsCurve()
