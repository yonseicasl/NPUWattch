#map0 = affine_map<(index0, index1) -> (index1 + 512 * index0)>
memref.global @buf0_spad : memref<16x512xf32, 1>
memref.global @buf1_spad : memref<16xf32, 1>
func.func @kernel(%in_ptr0: memref<8192xf32>,
                       %out_ptr0: memref<16xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 2 : index
    %const2 = arith.constant 0xff800000 : f32
    %const3 = vector.broadcast %const2 : f32 to vector<16xf32>
    %const4 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %spad0 = memref.get_global @buf0_spad : memref<16x512xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<16xf32, 1>
    affine.for %index0 = 0 to 16 step 16
    {
        %tmp_acc0 = affine.for %index1 = 0 to 512 step 512 iter_args(%iter0 = %const3) -> (vector<16xf32>)
        {
            %apply0 = affine.apply #map0(%index0, %index1) // // store_reduction=False
            memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0], %const1, %alloc0[%const0], %const0, %const1 : memref<8192xf32>, memref<16x512xf32, 1>, memref<1xi32> {dram_stride = [512, 1], sram_stride = [1, 16], padding = 0}
            %tmp_acc1 = affine.for %compute_idx = 0 to 1024 step 16 iter_args(%iter1 = %iter0) -> (vector<16xf32>)
            {
                %tmp1 = affine.vector_load %spad0[%const0,%compute_idx] : memref<16x512xf32, 1>, vector<16xf32>
                %tmp2 = arith.maximumf %tmp1, %iter1 : vector<16xf32>
                affine.yield %tmp2 : vector<16xf32>
            } {inner_loop=false}
            affine.yield %tmp_acc1 : vector<16xf32>
        } {accumulation_loop=true}
        %tmp3 = vector.broadcast %const2 : f32 to vector<2xf32>
        %tmp4 = vector.shape_cast %tmp_acc0 : vector<16xf32> to vector<8x2xf32>
        %tmp5 = vector.multi_reduction <maximumf>, %tmp4, %tmp3 [0] : vector<8x2xf32> to vector<2xf32>
        affine.vector_store %tmp5, %spad1[%const0] : memref<16xf32, 1>, vector<2xf32>
        memref.dma_start %spad1[%const0], %out_ptr0[%index0], %const4, %alloc1[%const0], %const0, %const1 : memref<16xf32, 1>, memref<16xf32>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
    } {outer_loop=true}
    return
}
