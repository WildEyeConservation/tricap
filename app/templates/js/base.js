// Code needed to make the base template work properly
// All of the following code will only run when the page is ready
//  (the $() is short for $(document).ready())

$(function(){

    $('#a_check_gps').on('click', function(event){
        $.getJSON($SCRIPT_ROOT + '/_check_gps',
                  {},
                  function(data){

                      // remove any existing GPS information pieces
                      if ($('#alt_gps').length > 0){
                          $('#alt_gps').remove();
                      }

                      var workingCount = 0;
                      var numCams = data.gps_status_of_cams.length;
                      for (var index = 0; index < numCams; index++){
                          if (data.gps_status_of_cams[index] === 'True'){
                              workingCount++;
                          }
                      }

                      var alertColour = 'alert-danger';

                      if (workingCount == numCams){
                          alertColour = 'alert-success';
                      } else if (workingCount > 0){
                          alertColour = 'alert-warning';
                      }

                      var outputStr = 'Cameras with active GPS: ' + workingCount + '/' + numCams;

                      var alertHtmlString = '<div class="alert ' + alertColour + ' alert-dismissable" id="alt_gps">' +
                                          outputStr +
                                          '<a href="#" class="close" data-dismiss="alert" aria-label="close">&times;</a>' +
                                          '</div>';

                      $('#base_container').append(alertHtmlString);

                      return true;
                  }
            );
        return true;
    });

    $('#a_check_sms').on('click', function(event){
        $.getJSON($SCRIPT_ROOT + '/_send_sms',

        function(data){
            // remove any existing GPS information pieces
            if ($('#alt_sms').length > 0){
                $('#alt_sms').remove();
            }

            var alertColour;
            var outputStr = data.message;
            if (data.success === true){
                alertColour = 'alert-success';

            } else {
                alertColour = 'alert-danger';
            }

            var alertHtmlString = '<div class="alert ' + alertColour + ' alert-dismissable" id="alt_sms">' +
                                outputStr +
                                '<a href="#" class="close" data-dismiss="alert" aria-label="close">&times;</a>' +
                                '</div>';

            $('#base_container').append(alertHtmlString);
        });
    });

});
