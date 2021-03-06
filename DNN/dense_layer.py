"""
arguments : num_outputs - > number of output neurons
            num_inputs -> number of input neurons
            relu -> activation function
            w -> weights
            b-> biases
            x -> input
            y -> output
            batch_size -> multiple inputs as a batch
            w_t -> gradient of w
            b_t -> gradient of b
            delta ->

*** Multiply and accumulate types of operations are generally subject to a
great loss of numerical precision. This can be mitigated by using a
temporary variable of higher precision to store values in the course of the
operation, and then typecasting this variable back to the original
precision after the operation is completed.
"""
from __future__ import division
import pycuda.autoinit
from pycuda import gpuarray
from pycuda.compiler import SourceModule
import numpy as np

DenseEvalCode = """
#define _RELU(x) ( ((x) > 0.0f) ? (x) : 0.0f )
#define _SIGMOID(x)  ( 1.0f / (1.0f + expf(-(x)) ))
__global__ void dense_eval(int num_outputs, int num_inputs, int relu, int sigmoid, float * w, float * b, \
                           float * x, float *y, int batch_size, int w_t, int b_t, float delta)
{
     int i = blockDim.x*blockIdx.x + threadIdx.x;
     
        
     if (i < num_outputs)
     {
         for(int k=0; k < batch_size; k++)
         {    
              double temp = 0.0f;
              
              for (int j = 0; j < num_inputs; j++)
              {
                  temp += ((double) w[ (num_inputs) * i + j ] ) * ( (double) x[k * num_inputs + j]);
              }
                  
              temp += (double) b[i];
              
              
              
              
              y[k * num_outputs + i] = (float) temp;                 
         }
    
         
        
        if( w_t >= 0 && i == (w_t / num_inputs))
        {
              int j = w_t % num_inputs;
              
              for(int k=0; k < batch_size; k++)
                  y[k*num_outputs + i] += delta*x[k*num_inputs+j];
                  
              
        }
         
        if( b_t >= 0 && i == b_t )
        {
              //int j = b_t % num_inputs;
              
              for(int k=0; k < batch_size; k++)
                  y[k*num_outputs + i] += delta;
        }
    
    
        if(relu > 0 || sigmoid > 0)
             for(int k=0; k < batch_size; k++)
             {    
                  float temp = y[k * num_outputs + i];
                  
                  if (relu > 0)
                      temp = _RELU(temp);
                      
                  if (sigmoid > 0)
                      temp = _SIGMOID(temp);
                  
                  
                  
                  
                  y[k * num_outputs + i] = temp;                 
             }
            
    
    }
    
    
         
    return;
}
"""

eval_mod = SourceModule(DenseEvalCode)
eval_ker = eval_mod.get_function('dense_eval')


class DenseLayer:

    def __init__(self, num_inputs=None,
                 num_outputs=None,
                 weights=None,
                 b=None,
                 stream=None,
                 relu=False,
                 sigmoid=False,
                 delta=None):
        self.stream = stream

        if delta is None:
            self.delta = np.float32(0.001)
        else:
            self.delta = np.float32(delta)

        if weights is None:
            self.weights = np.random.rand(num_outputs, num_inputs) - 0.5
            self.num_inputs = np.int32(num_inputs)
            self.num_outputs = np.int32(num_outputs)

        if type(weights) != pycuda.gpuarray.GPUArray:
            self.weights = gpuarray.to_gpu_async(np.array(weights),
                                                 stream=self.stream)
        else:
            self.weights = weights

        if num_inputs is None or num_outputs is None:

            self.num_inputs = np.int32(self.weights.shape[1])
            self.num_outputs = np.int32(self.weights.shape[0])

        else:
            self.num_inputs = np.int32(num_inputs)
            self.num_outputs = np.int32(num_outputs)

        if b is None:
            b = gpuarray.zeros((self.num_outputs,), dtype=np.float32)

        if type(b) != pycuda.gpuarray.GPUArray:
            self.b = gpuarray.to_gpu_async(np.array(b, dtype=np.float32), stream=self.stream)
        else:
            self.b = b

        self.relu = np.int32(relu)
        self.sigmoid = np.int32(sigmoid)
        self.block = (32, 1, 1)
        self.grid = (int(np.ceil(self.num_outputs / 32)), 1, 1)

    def eval_(self, x, y=None, batch_size=None, stream=None, delta=None,
             w_t=None, b_t=None):

        if stream is None:
            stream = self.stream
        if type(x) != pycuda.gpuarray.GPUArray:
            x = gpuarray.to_gpu_async(np.array(x, dtype=np.float32, stream=self.stream))
        if batch_size is None:
            delta = self.delta

        delta = np.float32(delta)
        if w_t is None:
            w_t = np.int32(-1)

        if b_t is None:
            b_t = np.int32(-1)

        if y is None:
            if batch_size == 1:
                y = gpuarray.empty((self.num_outputs,), dtype=np.float32)
            else:
                y = gpuarray.empty((batch_size, self.num_outputs), dtype=np.float32)

        eval_ker(self.num_outputs, self.num_inputs, self.relu, self.sigmoid,
                 self.weights, self.b, x, y, np.int32(batch_size), w_t, b_t,
                 delta, block=self.block, grid=self.grid, stream=stream)

        return y