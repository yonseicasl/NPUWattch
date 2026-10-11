#map0 = affine_map<(index0, index1) -> (index1 + 3136 * index0)>
memref.global @buf0_spad : memref<64x1792xf32, 1>
memref.global @buf1_spad : memref<64x1792xf32, 1>
memref.global @buf2_spad : memref<64x1792xf32, 1>
memref.global @buf3_spad : memref<64x1792xf32, 1>
memref.global @buf4_spad : memref<64x1792xf32, 1>
memref.global @buf5_spad : memref<64x1792xf32, 1>
func.func @kernel(%in_ptr0: memref<200704xf32>,
                       %in_ptr1: memref<64xf32>,
                       %in_ptr2: memref<64xf32>,
                       %in_ptr3: memref<64xf32>,
                       %in_ptr4: memref<64xf32>,
                       %out_ptr0: memref<200704xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 1 : index
    %const2 = arith.constant 2 : index
    %const3 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %alloc2 = memref.alloc() : memref<1xi32> // 2
    %alloc3 = memref.alloc() : memref<1xi32> // 3
    %alloc4 = memref.alloc() : memref<1xi32> // 4
    %alloc5 = memref.alloc() : memref<1xi32> // 5
    %spad0 = memref.get_global @buf0_spad : memref<64x1792xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<64x1792xf32, 1>
    %spad2 = memref.get_global @buf2_spad : memref<64x1792xf32, 1>
    %spad3 = memref.get_global @buf3_spad : memref<64x1792xf32, 1>
    %spad4 = memref.get_global @buf4_spad : memref<64x1792xf32, 1>
    %spad5 = memref.get_global @buf5_spad : memref<64x1792xf32, 1>
    affine.for %index0 = 0 to 64 step 64
    {
        affine.for %index1 = 0 to 3136 step 1792
        {
            %apply0 = affine.apply #map0(%index0, %index1) // // store_reduction=False
            memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0], %const2, %alloc0[%const0], %const1, %const2 : memref<200704xf32>, memref<64x1792xf32, 1>, memref<1xi32> {dram_stride = [3136, 1], sram_stride = [1792, 1], padding = 0}
            memref.dma_start %in_ptr1[%index0], %spad1[%const0,%const0], %const2, %alloc1[%const0], %const1, %const2 : memref<64xf32>, memref<64x1792xf32, 1>, memref<1xi32> {dram_stride = [1, 0], sram_stride = [1792, 1], padding = 0}
            memref.dma_start %in_ptr2[%index0], %spad2[%const0,%const0], %const2, %alloc2[%const0], %const1, %const2 : memref<64xf32>, memref<64x1792xf32, 1>, memref<1xi32> {dram_stride = [1, 0], sram_stride = [1792, 1], padding = 0}
            memref.dma_start %in_ptr3[%index0], %spad3[%const0,%const0], %const2, %alloc3[%const0], %const1, %const2 : memref<64xf32>, memref<64x1792xf32, 1>, memref<1xi32> {dram_stride = [1, 0], sram_stride = [1792, 1], padding = 0}
            memref.dma_start %in_ptr4[%index0], %spad4[%const0,%const0], %const2, %alloc4[%const0], %const1, %const2 : memref<64xf32>, memref<64x1792xf32, 1>, memref<1xi32> {dram_stride = [1, 0], sram_stride = [1792, 1], padding = 0}
            affine.for %compute_idx = 0 to 896 step 16
            {
                %tmp1 = affine.vector_load %spad0[%const0,%compute_idx] : memref<64x1792xf32, 1>, vector<16xf32>
                %tmp3 = affine.vector_load %spad1[%const0,%compute_idx] : memref<64x1792xf32, 1>, vector<16xf32>
                %tmp6 = affine.vector_load %spad2[%const0,%compute_idx] : memref<64x1792xf32, 1>, vector<16xf32>
                %tmp17 = affine.vector_load %spad3[%const0,%compute_idx] : memref<64x1792xf32, 1>, vector<16xf32>
                %tmp20 = affine.vector_load %spad4[%const0,%compute_idx] : memref<64x1792xf32, 1>, vector<16xf32>
                %tmp4 = arith.subf %tmp1, %tmp3 : vector<16xf32>
                %tmp7 = arith.constant 0.00001000000000000000 : f32
                %tmp8 = vector.broadcast %tmp7 : f32 to vector<16xf32>
                %tmp9 = arith.addf %tmp6, %tmp8 : vector<16xf32>
                %tmp10 = math.sqrt %tmp9 : vector<16xf32>
                %tmp11 = arith.constant 1.00000000000000000000 : f32
                %tmp12 = vector.broadcast %tmp11 : f32 to vector<16xf32>
                %tmp13 = arith.divf %tmp12, %tmp10 : vector<16xf32>
                %tmp14 = arith.mulf %tmp13, %tmp12 : vector<16xf32>
                %tmp15 = arith.mulf %tmp4, %tmp14 : vector<16xf32>
                %tmp18 = arith.mulf %tmp15, %tmp17 : vector<16xf32>
                %tmp21 = arith.addf %tmp18, %tmp20 : vector<16xf32>
                affine.vector_store %tmp21, %spad5[%const0,%compute_idx] : memref<64x1792xf32, 1>, vector<16xf32>
            } {inner_loop=false}
            memref.dma_start %spad5[%const0,%const0], %out_ptr0[%apply0], %const3, %alloc5[%const0], %const1, %const2 : memref<64x1792xf32, 1>, memref<200704xf32>, memref<1xi32> {dram_stride = [3136, 1], sram_stride = [1792, 1], padding = 0}
        } {outer_loop=true}
    } {outer_loop=true}
    return
}
