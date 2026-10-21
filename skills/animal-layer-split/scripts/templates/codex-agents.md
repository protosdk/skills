# Image edits in this folder

Every task in this folder edits an existing image; none asks for a new drawing.

When you call the image generation tool, always pass the image you were asked to edit (the attached file, as
an absolute path inside this folder) in `referenced_image_paths`, so the tool edits that exact image instead
of drawing a new one. Never call the image tool without that reference image.
