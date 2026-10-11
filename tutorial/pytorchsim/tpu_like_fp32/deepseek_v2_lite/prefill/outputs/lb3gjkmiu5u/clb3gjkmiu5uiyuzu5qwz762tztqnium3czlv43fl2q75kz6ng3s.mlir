
// BMM kernel
// BATCH = 64
// M = 48
// N = 2816
// K = 2048
// TILE_M = 48
// TILE_N = 2816
// TILE_K = 512
// SUB_TILE_M = 48
// SUB_TILE_N = 2816
memref.global @X_spad : memref<1x48x512xf32, 1>
memref.global @W_spad : memref<1x512x2816xf32, 1>
memref.global @Y_spad : memref<1x48x2816xf32, 1>
#t_map0 = affine_map<(d0, d1, d2) -> (135168*d0 + 2816*d1 + d2)>
#t_map1 = affine_map<(d0, d1, d2) -> (98304*d0 + 2048*d1 + d2)>
#t_map2 = affine_map<(d0, d1, d2) -> (5767168*d0 + 2816*d1 + d2)>

func.func @kernel(%X: memref<6291456xf32>, %W: memref<369098752xf32>, %Y: memref<8650752xf32>) {
  %X_buffer = memref.get_global @X_spad : memref<1x48x512xf32, 1>
  %W_buffer = memref.get_global @W_spad : memref<1x512x2816xf32, 1>
  %Y_buffer = memref.get_global @Y_spad : memref<1x48x2816xf32, 1>

  %v0 = arith.constant dense<0.0> : vector<1056xf32>

  %c0 = arith.constant 0 : index
  %t_const0 = arith.constant 0 : index
  %t_const1 = arith.constant 2 : index
  %t_const2 = arith.constant 1 : index
  %t_const3 = arith.constant 3 : index
  %t_alloc0 = memref.alloc() : memref<1xi32> // 0
  %t_alloc1 = memref.alloc() : memref<1xi32> // 1
  %t_alloc2 = memref.alloc() : memref<1xi32> // 2
  affine.for %index0 = 0 to 64 {
    affine.for %index1 = 0 to 48 step 48 {
      affine.for %index2 = 0 to 2816 step 2816 {
        %X_buffer2D = memref.reinterpret_cast %X_buffer to offset: [0], sizes: [48, 512], strides: [512, 1] : memref<1x48x512xf32, 1> to memref<48x512xf32, 1>
        %W_buffer2D = memref.reinterpret_cast %W_buffer to offset: [0], sizes: [512, 2816], strides: [2816, 1] : memref<1x512x2816xf32, 1> to memref<512x2816xf32, 1>
        %Y_buffer2D = memref.reinterpret_cast %Y_buffer to offset: [0], sizes: [48, 2816], strides: [2816, 1] : memref<1x48x2816xf32, 1> to memref<48x2816xf32, 1>
        affine.vector_store %v0, %Y_buffer[0, 0, 0] : memref<1x48x2816xf32, 1>, vector<1056xf32>


        affine.for %index3 = 0 to 2048 step 512 {
          %apply0 = affine.apply #t_map1(%index0, %index1, %index3)
          memref.dma_start %X[%apply0], %X_buffer[%t_const0, %t_const0, %t_const0], %t_const1, %t_alloc1[%t_const0], %t_const1, %t_const2 : memref<6291456xf32>, memref<1x48x512xf32, 1>, memref<1xi32> {dram_stride = [98304, 2048, 1], sram_stride = [0, 1, 48], padding = 0, subtile_size = [1, 48, 512], async = 1 : i64}
          %apply1 = affine.apply #t_map2(%index0, %index3, %index2)
          memref.dma_start %W[%apply1], %W_buffer[%t_const0, %t_const0, %t_const0], %t_const1, %t_alloc2[%t_const0], %t_const1, %t_const2 : memref<369098752xf32>, memref<1x512x2816xf32, 1>, memref<1xi32> {dram_stride = [5767168, 2816, 1], sram_stride = [0, 1, 512], padding = 0, subtile_size = [1, 512, 2816], async = 1 : i64}
          linalg.matmul ins(%X_buffer2D, %W_buffer2D : memref<48x512xf32, 1>, memref<512x2816xf32, 1>)
                  outs(%Y_buffer2D : memref<48x2816xf32, 1>)
        } { accumulation_loop=true, subtile_loop="k" }
        affine.for %compute_idx = 0 to 1 step 1
        {
        } {inner_loop=false}
        %epilogue_apply0 = affine.apply #t_map0(%index0, %index1, %index2)
        memref.dma_start %Y_buffer[%t_const0, %t_const0, %t_const0], %Y[%epilogue_apply0], %t_const3, %t_alloc0[%t_const0], %t_const1, %t_const2 : memref<1x48x2816xf32, 1>, memref<8650752xf32>, memref<1xi32> {dram_stride = [135168, 2816, 1], sram_stride = [0, 1, 48], padding = 0}
      } { outer_loop=true, subtile_loop="n" }
    } { outer_loop=true, subtile_loop="m" }
  } { outer_loop=true }
  return
}
