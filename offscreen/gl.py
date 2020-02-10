import ctypes
from OpenGL import GL
from OpenGL.GL.shaders import compileShader


class GLTextureRectangle:
    FLOAT_SIZE = ctypes.sizeof(GL.GLfloat)
    UINT_SIZE = ctypes.sizeof(GL.GLuint)

    VERTEX_SHADER = """
    #version 300 es
    layout (location = 0) in vec3 aPos;
    layout (location = 1) in vec2 aTexCoord;
    out vec2 ourTexCoord;

    void main()
    {
        gl_Position = vec4(aPos, 1.0);
        ourTexCoord = aTexCoord;
    }
    """

    FRAGMENT_SHADER = """
    #version 300 es
    precision mediump float;
    out vec4 FragColor;
    in vec2 ourTexCoord;
    uniform sampler2D ourTexture;
    
    void main()
    {
        FragColor = texture(ourTexture, ourTexCoord);
    }
    """

    VERTICES = [
        # // positions[3] + texture coordinates[2]
        1.0, 1.0, 0.0, 1.0, 1.0,  # top right
        1.0, -1.0, 0.0, 1.0, 0.0,  # bottom right
        -1.0, -1.0, 0.0, 0.0, 0.0,  # bottom left
        -1.0, 1.0, 0.0, 0.0, 1.0  # top left
    ]

    INDICES = [
        0, 1, 2,  # first triangle
        0, 2, 3,  # second triangle
    ]

    def __init__(self) -> None:
        self.glProg = prog = GL.glCreateProgram()
        vertex_shader = compileShader(self.VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        GL.glAttachShader(prog, vertex_shader)
        fragment_shader = compileShader(self.FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        GL.glAttachShader(prog, fragment_shader)
        GL.glLinkProgram(prog)
        GL.glDeleteShader(vertex_shader)
        GL.glDeleteShader(fragment_shader)
        GL.glUseProgram(self.glProg)
        GL.glUniform1i(GL.glGetUniformLocation(self.glProg, "ourTexture"), 0)

        self.glVertexArray = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.glVertexArray)

        self.glElementBuffer = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.glElementBuffer)
        array_type = (GL.GLuint * len(self.INDICES))
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, len(self.INDICES) * self.UINT_SIZE,
                        array_type(*self.INDICES), GL.GL_STATIC_DRAW)

        self.glVertexBuffer = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.glVertexBuffer)
        array_type = (GL.GLfloat * len(self.VERTICES))
        GL.glBufferData(GL.GL_ARRAY_BUFFER, len(self.VERTICES) * self.FLOAT_SIZE,
                        array_type(*self.VERTICES), GL.GL_STATIC_DRAW)

        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, False, 5 * self.FLOAT_SIZE, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, False, 5 * self.FLOAT_SIZE, ctypes.c_void_p(3 * self.FLOAT_SIZE))
        GL.glEnableVertexAttribArray(1)

        GL.glBindVertexArray(0)

    def draw(self, textureId: int) -> None:
        GL.glClearColor(0.2, 0.3, 0.3, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glUseProgram(self.glProg)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, textureId)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_BORDER)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_BORDER)
        GL.glBindVertexArray(self.glVertexArray)
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
