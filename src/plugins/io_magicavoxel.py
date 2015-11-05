# io_magica.py
# MagicaVoxel Binary File IO
# Copyright (c) 2015, Henrik Andersson
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

from plugin_api import register_plugin

class MagicaVoxelFile(object):

    # Description of file type
    description = "MagicaVoxel Files"

    # File type filter
    filetype = "*.vox"

    def __init__(self, api):
        self.api = api
        # Register our exporter
        self.api.register_file_handler(self)

    # Helper function to read/write uint32
    def uint32(self, f, value = None):
        if value is not None:
            # Write
            data = bytearray()
            data.append((value & 0xff))
            data.append((value & 0xff00)>>8)
            data.append((value & 0xff0000)>>16)
            data.append((value & 0xff000000)>>24)
            f.write(data)
        else:
            # Read
            x = bytearray(f.read(4))
            if len(x) == 4:
                return x[0] | x[1]<<8 | x[2]<<16 | x[3]<<24
            return 0

    def string(self, f, value):
        data = bytearray()
        data.extend(value)
        f.write(data)

    # Called when we need to save. Should raise an exception if there is a
    # problem saving.
    def save(self, filename):

        voxels = self.api.get_voxel_data()

        # count the number of voxels and construct a palette to be
        # used for indexed colored voxels
        voxel_count = 0
        paletteMap = {}
        palette = {}
        idx = 0
        for z in xrange(voxels.depth):
            for y in xrange(voxels.height):
                for x in xrange(voxels.width):
                    vox = voxels.get(x,y,z)
                    if vox:
                        color = (vox & 0xffffff00)
                        if not color in palette.keys():
                            paletteMap[color] = idx
                            palette[idx] = color
                            idx = idx + 1
                        voxel_count = voxel_count + 1

        # handle palette bigger than 255 entries
        if idx >= 256:
            raise Exception("Model uses %d uniq colors, which exceeds palette size." % idx)

        self.api.warning("Identified %d number of uniq colors in model." % idx)

        # calculate sizes for each chunks to be written to file
        chunk_size = 16 + 4 * 3
        chunk_rgba = 16 + 4 * 256
        chunk_voxel = 16 + 4 + (voxel_count) * 4
        chunk_main = 16 + chunk_size + chunk_rgba + chunk_voxel

        f = open(filename,"wb")

        # write header
        self.string(f, "VOX ")
        self.uint32(f, 150)

        # write main chunk
        self.string(f, "MAIN")
        self.uint32(f, 0)
        self.uint32(f, chunk_main)

        # write dimension chunk
        self.string(f, "SIZE")
        self.uint32(f, 4*3)
        self.uint32(f, 0)
        self.uint32(f, voxels.width)
        self.uint32(f, voxels.height)
        self.uint32(f, voxels.depth)

        # write palette chunk
        self.string(f, "RGBA")
        self.uint32(f, 4 * 256)
        self.uint32(f, 0)
        for i in xrange(256):
            b = bytearray()
            if i in palette.keys():
                color = palette[i]
                b.extend([(color & 0xff000000) >> 24,
                          (color & 0xff0000) >> 16,
                          (color & 0xff00) >> 8, 0xff])
            else:
                b.extend([0xff, 0xff, 0xff, 0xff])
            f.write(b)

        # write voxel chunk
        self.string(f, "XYZI")
        self.uint32(f, 4 + (voxel_count * 4))
        self.uint32(f, 0)
        self.uint32(f, voxel_count)

        for z in xrange(voxels.depth):
            for y in xrange(voxels.height):
                for x in xrange(voxels.width):
                    vox = voxels.get(x, z, y)
                    if not vox:
                        continue

                    # Get color index in palette, use 0 if not found
                    # as fallback
                    if (vox&0xffffff00) in paletteMap.keys():
                        cidx = paletteMap[vox&0xffffff00]
                    else:
                        cidx = 0

                    # Write voxel to file
                    v = bytearray()
                    v.extend([x, y, z, cidx])
                    f.write(v)

        # Tidy up
        f.close()


    def load(self, filename):
        palette = {}
        voxels = self.api.get_voxel_data()

        f = open(filename,"rb")

        # Read header
        magic = f.read(4)
        version = self.uint32(f)
        if not magic == "VOX ":
            raise Exception("Not an MagicaVoxel file")

        # read main chunk header
        cid = f.read(4)
        content_size = self.uint32(f)
        child_size = self.uint32(f)

        # read child chunks of main header
        left = content_size + child_size
        while left:
            cid = f.read(4)
            content_size = self.uint32(f)
            child_size = self.uint32(f)
            left = left - 16


            if cid == "SIZE":
                # Read and parser dimension chunk
                width = self.uint32(f)
                height = self.uint32(f)
                depth = self.uint32(f)

                if width > 127 or height > 127 or depth > 127:
                    raise Exception("Model to large - max 127x127x127")

                voxels.resize(width, height, depth)

            elif cid == "RGBA":
                # Read and parse palette chunk
                for i in xrange(256):
                    b = bytearray()
                    b.extend(f.read(4))
                    palette[i] = b[0] << 24 | b[1] << 16 | b[2] << 8 | b[3]

            elif cid == "XYZI":
                # Read and parse voxels chunk
                voxel_count = self.uint32(f)
                for i in xrange(voxel_count):
                    b = bytearray()
                    b.extend(f.read(4))

                    color = 0xffffffff
                    if b[3] in palette.keys():
                        color = palette[b[3]]

                    voxels.set(b[0],b[2],b[1],color);

            else:
                # Skip unknown/unhandled chunks
                f.read(content_size + child_size)

            left = left - content_size + child_size

        f.close()


register_plugin(MagicaVoxelFile, "MagicaVoxel file format IO", "1.0")
