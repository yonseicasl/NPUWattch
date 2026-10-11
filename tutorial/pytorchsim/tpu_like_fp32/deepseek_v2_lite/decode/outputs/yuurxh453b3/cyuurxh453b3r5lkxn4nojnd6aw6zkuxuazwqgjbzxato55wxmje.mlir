memref.global @buf0_spad : memref<1024xf32, 1>
memref.global @buf1_spad : memref<1024xf32, 1>
memref.global @buf2_spad : memref<1024xf32, 1>
memref.global @buf3_spad : memref<1024xf32, 1>
func.func @kernel(%in_ptr0: memref<2048xf32>,
                       %in_ptr1: memref<1xf32>,
                       %in_ptr2: memref<2048xf32>,
                       %out_ptr0: memref<2048xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 4 : index
    %const2 = arith.constant 2 : index
    %const3 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %alloc2 = memref.alloc() : memref<1xi32> // 2
    %alloc3 = memref.alloc() : memref<1xi32> // 3
    %spad0 = memref.get_global @buf0_spad : memref<1024xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<1024xf32, 1>
    %spad2 = memref.get_global @buf2_spad : memref<1024xf32, 1>
    %spad3 = memref.get_global @buf3_spad : memref<1024xf32, 1>
    affine.for %index0 = 0 to 2048 step 1024
    {
        memref.dma_start %in_ptr0[%index0], %spad0[%const0], %const2, %alloc0[%const0], %const0, %const1 : memref<2048xf32>, memref<1024xf32, 1>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
        memref.dma_start %in_ptr1[%const0], %spad1[%const0], %const2, %alloc1[%const0], %const0, %const1 : memref<1xf32>, memref<1024xf32, 1>, memref<1xi32> {dram_stride = [0], sram_stride = [1], padding = 0}
        memref.dma_start %in_ptr2[%index0], %spad2[%const0], %const2, %alloc2[%const0], %const0, %const1 : memref<2048xf32>, memref<1024xf32, 1>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
        affine.for %compute_idx = 0 to 8 step 4
        {
            %tmp1 = affine.vector_load %spad0[%compute_idx] : memref<1024xf32, 1>, vector<4xf32>
            %tmp3 = affine.vector_load %spad1[%compute_idx] : memref<1024xf32, 1>, vector<4xf32>
            %tmp13 = affine.vector_load %spad2[%compute_idx] : memref<1024xf32, 1>, vector<4xf32>
            %tmp4 = arith.constant 2048.00000000000000000000 : f32
            %tmp5 = vector.broadcast %tmp4 : f32 to vector<4xf32>
            %tmp6 = arith.divf %tmp3, %tmp5 : vector<4xf32>
            %tmp7 = arith.constant 0.00000100000000000000 : f32
            %tmp8 = vector.broadcast %tmp7 : f32 to vector<4xf32>
            %tmp9 = arith.addf %tmp6, %tmp8 : vector<4xf32>
            %tmp10 = math.rsqrt %tmp9 : vector<4xf32>
            %tmp11 = arith.mulf %tmp1, %tmp10 : vector<4xf32>
            %tmp14 = arith.mulf %tmp11, %tmp13 : vector<4xf32>
            affine.vector_store %tmp14, %spad3[%compute_idx] : memref<1024xf32, 1>, vector<4xf32>
        } {inner_loop=false}
        memref.dma_start %spad3[%const0], %out_ptr0[%index0], %const3, %alloc3[%const0], %const0, %const1 : memref<1024xf32, 1>, memref<2048xf32>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
    } {outer_loop=true}
    return
}
